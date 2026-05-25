# Project Flow — End to End

This document explains **how the whole system works together** in plain English:
what each container does, how a file travels from your browser into a Windmill workflow and
back into the database, how to push/pull workflows into Windmill, and the small "gotchas"
that trip everyone up the first time.

If you just want to **run** the project, read [README.md](README.md) first.
If you want to **understand** it, you're in the right place.

---

## 1. The cast of characters

The project runs as 4 containers (think of them as 4 separate small computers, all on
the same private network):

| Container | Real name | Job | You access it at |
|---|---|---|---|
| **API** | `fastapi_windmill_api` | The FastAPI backend — handles login, uploads, RBAC, triggers Windmill | <http://localhost:8000> |
| **DB** | `fastapi_windmill_postgres` | PostgreSQL — stores users, uploads, audit logs, and the split department data | `localhost:5432` |
| **Windmill server** | `windmill_server` | Windmill's web UI and REST API | <http://localhost:8080> |
| **Windmill worker** | `windmill_worker` | The thing that actually runs your workflow code | (internal only) |

**Two shared "drives" make the magic work:**

| Volume | Mounted in | Purpose |
|---|---|---|
| `upload_data` | API (read/write) **and** Windmill worker (read-only) | When FastAPI writes a file to `/data/uploads`, the Windmill worker can read that same file. This is how the file gets from FastAPI to Windmill — they share a folder. |
| `postgres_data` | DB | Persists both databases (`loan_db` for the app, `windmill` for Windmill itself) across container restarts. |

**One database, two schemas:**

- `loan_db` — created by [docker-entrypoint-initdb.d/01-create-windmill-db.sql](docker-entrypoint-initdb.d/01-create-windmill-db.sql) — used by FastAPI.
- `windmill` — same SQL file creates this too — used by Windmill to store flows, runs, and logs.

---

## 2. The whole journey, in one picture

```text
   ┌─────────┐
   │ Browser │
   │  / curl │
   └────┬────┘
        │  (1) POST /api/v1/auth/login
        ▼
   ┌────────────────────────────────────────────────────────────┐
   │                    FastAPI (api container)                  │
   │                                                            │
   │  AuthService → issues a JWT (signed, ~30 min lifetime)     │
   │                                                            │
   │  (2) POST /api/v1/uploads/loan with Authorization: Bearer  │
   │      ─────────────────────────────────────────             │
   │      get_current_user → decode JWT, re-load user from DB   │
   │      require_roles(admin) → 403 if not admin               │
   │      UploadService.upload_and_trigger():                   │
   │        • validate extension / size / sanitize filename     │
   │        • write file → /data/uploads/<uuid>-<name>          │
   │        • INSERT file_uploads (status = "stored")           │
   │        • INSERT audit_logs (action = "file.stored")        │
   │        • read department_settings table for emails         │
   │        • WindmillService.trigger_upload_workflow() ───┐    │
   └───────────────────────────────────────────────────────┼────┘
                                                          │
                            (3) POST /api/w/{ws}/jobs/run/f/u/admin/loan_pipeline
                                Authorization: Bearer <WINDMILL_TOKEN>
                                Body: { upload_id, file_path, user, ingest_url,
                                        ingest_token, department_emails, smtp_config }
                                                          │
                                                          ▼
   ┌────────────────────────────────────────────────────────────┐
   │           Windmill server + worker (two containers)         │
   │                                                            │
   │  • Server accepts the job, queues it                       │
   │  • Worker picks it up and runs the flow:                   │
   │      1. Read CSV from /data/uploads/<uuid>-<name>           │
   │         (shared volume — same file FastAPI wrote)          │
   │      2. Split rows into finance / hr / sales               │
   │      3. Send emails via smtp_config → department_emails    │
   │      4. POST results back to FastAPI ────────────┐         │
   └──────────────────────────────────────────────────┼─────────┘
                                                     │
                      (4) POST /api/v1/internal/ingest
                          Header: X-Ingest-Token: <INGEST_TOKEN>
                          Body: { finance: [...], hr: [...], sales: [...] }
                                                     │
                                                     ▼
   ┌────────────────────────────────────────────────────────────┐
   │                    FastAPI (api container)                  │
   │                                                            │
   │  _verify_ingest_token → reject unless token matches        │
   │  INSERT into finance_data / hr_data / sales_data           │
   │  Return per-department insert counts                       │
   └────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
   ┌────────────────────────────────────────────────────────────┐
   │                  PostgreSQL  (loan_db)                      │
   │  users · file_uploads · audit_logs ·                       │
   │  department_settings · finance_data · hr_data · sales_data │
   └────────────────────────────────────────────────────────────┘
                          ▲
   (5) GET /api/v1/data/me ┘   admin → sees all departments
                                finance/hr/sales user → only their own
```

---

## 3. Phase-by-phase walkthrough

### Phase 0 — Startup (happens once, when `api` starts)

Code: [app/main.py](app/main.py) — the `lifespan()` async context manager.

1. **`create_database_schema()`** — runs `Base.metadata.create_all()` to create every table
   if it doesn't exist. (In production you'd swap this for Alembic migrations.)
2. **`seed_demo_users()`** — inserts the 4 demo users (admin, finance_user, hr_user,
   sales_user) **only if they don't already exist**. Never overwrites.
3. **`seed_department_settings()`** — inserts one row per department into
   `department_settings`, reading emails from `.env` (`FINANCE_EMAIL`, `HR_EMAIL`, `SALES_EMAIL`).
   Again — **only if the row is missing**. This is gotcha #1 (see §7).

### Phase 1 — Authentication

| Endpoint | What it does |
|---|---|
| `POST /api/v1/auth/register` | Hash password, insert into `users` |
| `POST /api/v1/auth/login` | Verify password, return a signed JWT |

The JWT contains just `sub` (username) and an expiry. **It does not contain the role.**
On every protected request, [app/api/dependencies.py](app/api/dependencies.py) `get_current_user()`:
1. Decodes the JWT (using `SECRET_KEY`).
2. Reads `sub` (the username).
3. Looks the user up in PostgreSQL **right now**.
4. Checks `is_active`.

This means if you disable a user in the DB, their token immediately stops working — Postgres is
the source of truth, not the token.

### Phase 2 — Upload and trigger (the heart of the system)

Endpoint: `POST /api/v1/uploads/loan` — [app/api/v1/routers/uploads.py](app/api/v1/routers/uploads.py)

Step-by-step, when an admin uploads a file:

1. **RBAC check** — `require_roles(Role.admin)` ([app/core/rbac.py](app/core/rbac.py)).
   Any other role → `403 Forbidden`.

2. **`UploadService.upload_and_trigger()`** — [app/services/upload_service.py](app/services/upload_service.py):

   - **Validate extension** against `ALLOWED_UPLOAD_EXTENSIONS` from `.env`. Bad type → `400`.
   - **Sanitize filename** → save as `/data/uploads/<uuid>-<safe_name><ext>`.
     (The UUID prefix prevents collisions and stops path-traversal tricks.)
   - **Stream the file to disk**, enforcing `MAX_UPLOAD_BYTES`. Too big → `413`.
   - **`INSERT INTO file_uploads`** with `status = 'stored'`.
   - **`INSERT INTO audit_logs`** with `action = 'file.stored'` — the audit trail.
   - **Read `department_settings`** table (a `SELECT`) for the current notification emails.
   - **Call `WindmillService.trigger_upload_workflow()`** — see next step.

3. **`WindmillService.trigger_upload_workflow()`** — [app/services/windmill_service.py](app/services/windmill_service.py):

   - If `WINDMILL_MOCK=true` → returns a fake `mock-<uuid>` job ID, no HTTP call.
     (Useful for local dev when you don't want to run Windmill.)
   - Otherwise:
     ```
     POST {WINDMILL_BASE_URL}/api/w/{WINDMILL_WORKSPACE}/jobs/run/f/{WINDMILL_WORKFLOW_PATH}
     Authorization: Bearer {WINDMILL_TOKEN}
     ```
     With this JSON body:

     | Field | Where it comes from |
     |---|---|
     | `upload_id` | The new `file_uploads` row's ID |
     | `file_path` | `/data/uploads/<uuid>-<name>` — the shared-volume path |
     | `original_filename` | What the user uploaded |
     | `user` | The caller's username |
     | `ingest_url` | `INGEST_CALLBACK_URL` from `.env` |
     | `ingest_token` | `INGEST_TOKEN` from `.env` (used to authenticate the callback) |
     | `department_emails` | From the `department_settings` **table** |
     | `smtp_config` | All `SMTP_*` **env vars** |

   - Windmill returns a job UUID immediately (it queues the work; doesn't wait for it to finish).

4. **Update upload status:**
   - Success → `file_uploads.status = 'workflow_triggered'`, `windmill_job_id = <uuid>`,
     audit log `workflow.triggered`.
   - Exception → `file_uploads.status = 'workflow_failed'`, exception re-raised so the user sees the error.

5. **Return the response** to the user (with `upload_id`, `status`, `windmill_job_id`).
   The user's request ends here — the rest is async.

### Phase 3 — Windmill runs the flow

The flow `u/admin/loan_pipeline` lives **inside Windmill's database**, not in this repo.
[windmill-flow.json](windmill-flow.json) is just a starter template you can import.

A typical flow does:

1. **Read the CSV** from `file_path`. This works because the `upload_data` volume is mounted
   in both the API container (read/write) and the Windmill worker (read-only) — they share the
   same `/data/uploads` folder.
2. **Split rows** into finance / hr / sales buckets.
3. **Send a notification email** per department, using `smtp_config` → `department_emails`.
4. **Call back FastAPI** to save the data:
   ```
   POST {ingest_url}
   X-Ingest-Token: {ingest_token}
   Body: { "finance": [...], "hr": [...], "sales": [...] }
   ```

### Phase 4 — Ingest callback (Windmill → FastAPI)

Endpoint: `POST /api/v1/internal/ingest` — [app/api/v1/routers/internal.py](app/api/v1/routers/internal.py)

1. **`_verify_ingest_token`** checks `X-Ingest-Token` matches `INGEST_TOKEN` from `.env`.
   Mismatch → `401`. This is how FastAPI knows "yes, this is really my Windmill calling me back,
   not a random attacker on the internet."
2. For each department in the payload, `INSERT` rows into the matching table
   (`finance_data`, `hr_data`, or `sales_data`).
3. Return per-department counts.

### Phase 5 — Reading the data back

Endpoints: `GET /api/v1/data/me` and `GET /api/v1/data/{department}` —
[app/api/v1/routers/data.py](app/api/v1/routers/data.py)

The RBAC scoping is the whole point of the system:

| User logged in as | What `GET /data/me` returns |
|---|---|
| `admin` | **All** rows from all 3 tables |
| `finance_user` | Only rows from `finance_data` |
| `hr_user` | Only rows from `hr_data` |
| `sales_user` | Only rows from `sales_data` |

Asking for a department that doesn't match your role → `403`. Unknown department → `404`.

---

## 4. How to push/pull Windmill flows

Windmill flows aren't stored in this repo — they live in Windmill's own database.
Here's how to move them around.

### Option A — Use the Windmill UI (easiest, no CLI needed)

**To create the flow the first time:**

1. Open <http://localhost:8080>.
2. First-time setup: create an account (it becomes the workspace admin).
3. Create a workspace named `loan` (or whatever matches your `.env`'s `WINDMILL_WORKSPACE`).
4. Go to **Flows → +New flow → Import from JSON**.
5. Paste the contents of [windmill-flow.json](windmill-flow.json) and save as `u/admin/loan_pipeline`
   (the path must match `WINDMILL_WORKFLOW_PATH` in `.env`).

**To export a flow you've edited:**

1. Open the flow in the Windmill UI.
2. Click **⋮ → Export → Download JSON**.
3. Save it over [windmill-flow.json](windmill-flow.json) and commit to git so your team has it.

### Option B — Use the Windmill CLI (`wmill`) for proper push/pull

The `wmill` CLI treats Windmill workspaces like a git remote — you can `push` local files
**to** Windmill and `pull` everything **from** Windmill into your filesystem.

```powershell
# Install (one time) — requires Deno: https://deno.land/
deno install -A -f -n wmill https://deno.land/x/wmill/main.ts

# Configure once — uses your WINDMILL_TOKEN from .env
wmill workspace add loan loan http://localhost:8080

# PULL everything from Windmill into the current directory
wmill sync pull

# PUSH local changes (flows, scripts, resources) back into Windmill
wmill sync push
```

This is the workflow for serious development — you edit flow JSON files locally, version
them in git, and `wmill sync push` to deploy.

### Option C — REST API (what `install-dashboard.ps1` does)

You can `POST` directly to Windmill's REST API. See [install-dashboard.ps1](install-dashboard.ps1)
and [install-dashboard.py](install-dashboard.py) for working examples — they install the
dashboard app into Windmill via raw HTTP calls.

### Getting a Windmill token

To call Windmill's API (whether via `wmill`, `install-dashboard.ps1`, or your own scripts):

1. Open <http://localhost:8080>.
2. Click your avatar (top right) → **Account settings → Tokens → +New token**.
3. Copy the token and paste it into `.env` as `WINDMILL_TOKEN=wm_...`.
4. **Important:** restart the API container so it picks up the new value:
   ```powershell
   docker compose up -d --force-recreate api
   ```

---

## 5. The live dashboard (Windmill App)

[windmill-app-dashboard.json](windmill-app-dashboard.json) is a ready-made Windmill App
that gives you a live view of every pipeline run: stat cards, sortable runs table, per-job
detail panel with step badges, and a colourised log stream.

**Install it (one command):**

```powershell
.\install-dashboard.ps1
```

[install-dashboard.ps1](install-dashboard.ps1) reads `WINDMILL_PUBLIC_URL`, `WINDMILL_WORKSPACE`,
and `WINDMILL_TOKEN` from `.env`, then POSTs to `/api/w/{ws}/apps/create` (or `/apps/update/{path}`
if it already exists). When it prints `Created.`, the dashboard is live at:

```text
http://localhost:8080/apps/get/u/admin/loan_dashboard
```

**Layout:**

```text
┌──────────────────────────────────────────────────────────────┐
│ Loan Pipeline Dashboard            Flow: u/admin/loan_pipeline│
├─────────────┬─────────────┬─────────────┬───────────────────┤
│ Total runs  │  Running    │  Succeeded  │  Failed           │
│     42      │      1      │     38      │      3            │
├─────────────┴─────────────┴─────────────┴───────────────────┤
│ [Refresh now]   Last updated: …   Auto-refresh every 5s     │
├──────────────────────────────────────────────────────────────┤
│ Started ▼ │ Job ID │ User  │ Status   │ Dur  │ Upload       │
│ 12:04:11  │ a1b2…  │ admin │ Running  │ 3.1s │ loans.csv    │
│ 11:58:02  │ 8e9f…  │ admin │ Success  │ 4.7s │ q3.csv       │
├──────────────────────┬──────────────────────────────────────┤
│ Selected job         │ Flow logs        <uuid>… get_flow_… │
│  <uuid>              │ INFO  Started flow                   │
│  Started: 12:04:11   │ INFO  process_upload OK              │
│  Duration: 3.12s     │ INFO  email sent (finance)           │
│  Upload: loans.csv   │ WARN  retry hr SMTP                  │
│  Steps:              │ ERROR no rows for sales              │
│   • process_upload ✓ │ INFO  ingest OK (12 rows)            │
│   • split_rows  ▶    │                                      │
│  [Open in Windmill ↗]│                                      │
└──────────────────────┴──────────────────────────────────────┘
```

**Manual alternative** (if you don't want to run the script): open Windmill →
**Apps → +New → Import from JSON** → paste [windmill-app-dashboard.json](windmill-app-dashboard.json).

---

## 6. Exposing Windmill to the public internet (ngrok)

Useful if you want Windmill to receive webhooks from real services, or if you want to share
your local Windmill with a teammate.

```powershell
# 1. Put your ngrok token in .env
#    Get one free at https://dashboard.ngrok.com/get-started/your-authtoken
#    NGROK_AUTHTOKEN=2abc...

# 2. Start the ngrok tunnel (it's an optional profile, not started by default)
docker compose --profile tunnel up -d ngrok_windmill

# 3. Find your public URL
docker compose logs ngrok_windmill | Select-String "url="

# 4. Or use the ngrok inspector
start http://localhost:4040
```

Update `WINDMILL_PUBLIC_URL` in `.env` to the ngrok URL, then recreate the Windmill server
so it generates webhook URLs using the public domain:

```powershell
docker compose up -d --force-recreate windmill_server
```

---

## 7. The config gotcha everyone hits

Not all config in `.env` reaches the running app the same way. This is the #1 cause of
"I changed `.env` but nothing updated" confusion:

| Config | How it's read | To change it on a running system |
|---|---|---|
| `SMTP_*`, `WINDMILL_*`, `INGEST_*` | Read **live from env vars** on every workflow trigger | Edit `.env` then `docker compose up -d --force-recreate api` |
| `FINANCE_EMAIL` / `HR_EMAIL` / `SALES_EMAIL` | Only used to **seed** `department_settings` on first boot — ignored after that | `UPDATE department_settings SET email='...' WHERE department='...';` |

**Why a plain `restart` doesn't work:**

- `docker-compose.yml` has `env_file: .env`. Docker reads `.env` and **snapshots** it into the
  container's environment at **container-create time**.
- A running container keeps that snapshot. `docker compose restart api` reuses the same
  container — same snapshot. Nothing re-reads `.env`.
- Only `--force-recreate` (or `down` + `up`) destroys the container and creates a new one
  with fresh env values.
- Even though the project folder is bind-mounted into `/app` (so the file inside is up to date),
  `pydantic-settings` prefers real env vars over the file — so the frozen snapshot wins.

**Update department emails on a running system without restarting:**

```powershell
docker exec fastapi_windmill_postgres psql -U postgres -d loan_db -c `
  "UPDATE department_settings SET email='new@example.com' WHERE department='finance';"
```

---

## 8. The data model

Database: `loan_db` (created by [docker-entrypoint-initdb.d/01-create-windmill-db.sql](docker-entrypoint-initdb.d/01-create-windmill-db.sql)).

| Table | Written by | Purpose |
|---|---|---|
| `users` | register endpoint / `seed_demo_users` | Accounts, hashed password, role, active flag |
| `file_uploads` | `UploadService` | One row per upload — status, filename, Windmill job ID |
| `audit_logs` | `AuditService` | Append-only audit trail (every login, every upload, every trigger) |
| `department_settings` | `seed_department_settings` (once) | Per-department notification email — editable via SQL |
| `finance_data` | `/internal/ingest` (called by Windmill) | Finance rows extracted from uploaded CSVs |
| `hr_data` | `/internal/ingest` | HR rows |
| `sales_data` | `/internal/ingest` | Sales rows |

**`file_uploads.status` lifecycle:**

```text
stored ──► workflow_triggered    (Windmill accepted the job)
      └──► workflow_failed       (the trigger call raised an exception)
```

Note: `workflow_triggered` only means **Windmill accepted the job**, not that it succeeded.
To see whether the flow actually completed, check the Windmill UI or the dashboard app.

---

## 9. End-to-end smoke test (paste into PowerShell)

This proves the entire pipeline works from login to ingested data:

```powershell
# 1. Login as the seeded admin
$token = (Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method Post `
  -ContentType 'application/json' `
  -Body '{"username":"admin","password":"admin1234"}').access_token

# 2. Upload a loan file (triggers the Windmill flow)
Invoke-RestMethod -Uri http://localhost:8000/api/v1/uploads/loan -Method Post `
  -Headers @{ Authorization = "Bearer $token" } `
  -Form @{ file = Get-Item .\sample.csv }

# 3. Inspect what was recorded
docker exec fastapi_windmill_postgres psql -U postgres -d loan_db -c `
  "SELECT id, status, windmill_job_id FROM file_uploads ORDER BY id DESC LIMIT 3;"

# 4. Wait ~5 seconds for the flow to finish, then read the ingested data
Start-Sleep -Seconds 5
Invoke-RestMethod -Uri http://localhost:8000/api/v1/data/me -Method Get `
  -Headers @{ Authorization = "Bearer $token" }

# 5. Confirm a non-admin user only sees their slice
$financeToken = (Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method Post `
  -ContentType 'application/json' `
  -Body '{"username":"finance_user","password":"finance1234"}').access_token
Invoke-RestMethod -Uri http://localhost:8000/api/v1/data/me -Method Get `
  -Headers @{ Authorization = "Bearer $financeToken" }
```

If step 4 returns rows and step 5 returns **only** finance rows — you're fully working.

---

## 10. Where to look when something breaks

| Symptom | First thing to check |
|---|---|
| Upload returns success but no data shows up | `docker compose logs windmill_worker` — is the flow erroring? |
| Windmill returns 401 to FastAPI | `WINDMILL_TOKEN` expired or wrong — generate a new one |
| Windmill returns 404 | `WINDMILL_WORKSPACE` or `WINDMILL_WORKFLOW_PATH` mismatch |
| Ingest callback returns 401 | `INGEST_TOKEN` mismatch between FastAPI and the flow's payload |
| Emails never arrive | SMTP credentials wrong (use a Gmail [App Password](https://myaccount.google.com/apppasswords), not your real password) |
| Department emails are stale | You edited `.env` — but the table was already seeded. UPDATE the table directly. |
| `.env` changes ignored | Run `docker compose up -d --force-recreate api` instead of `restart` |
| `file not found` in the worker | Check the worker has `upload_data:/data/uploads:ro` mounted; restart it |

---

## 11. The endpoint reference card

| Method | Path | Auth | Allowed roles |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | none | anyone |
| `POST` | `/api/v1/auth/login` | none | anyone |
| `POST` | `/api/v1/uploads/loan` | Bearer JWT | `admin` |
| `POST` | `/api/v1/internal/ingest` | `X-Ingest-Token` header | (called by Windmill only) |
| `GET` | `/api/v1/data/me` | Bearer JWT | any (scoped by role) |
| `GET` | `/api/v1/data/{department}` | Bearer JWT | `admin` or matching dept user |
| `GET` | `/api/v1/health/live` | none | anyone |
| `GET` | `/api/v1/health/ready` | none | anyone |

Full live docs: <http://localhost:8000/docs>
