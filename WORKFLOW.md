# End-to-End Workflow

How a loan file travels from an HTTP upload, through FastAPI, into a Windmill flow,
and back into PostgreSQL — plus every piece of config that influences it.

---

## 1. System components

| Service | Container | Role |
|---|---|---|
| `api` | `fastapi_windmill_api` | FastAPI app — auth, RBAC, file storage, triggers Windmill, receives ingest callback |
| `db` | `fastapi_windmill_postgres` | PostgreSQL — hosts **two** databases: `loan_db` (app) and `windmill` (Windmill's own) |
| `windmill_server` | `windmill_server` | Windmill UI/API at `http://localhost:8080` |
| `windmill_worker` | `windmill_worker` | Executes the flow; mounts `/data/uploads` **read-only** |
| `ngrok_windmill` | `ngrok_windmill` | Optional public tunnel (profile `tunnel`) |

**Shared volumes that make the workflow possible:**
- `upload_data` → mounted at `/data/uploads` in both `api` (read/write) and `windmill_worker` (read-only). This is how Windmill reads the file FastAPI wrote.
- `postgres_data` → persists both databases across restarts.

---

## 2. The big picture

```text
                        ┌─────────────────────────────────────────────┐
   curl / React         │                  FastAPI api                │
   ──────────────►      │                                             │
   1. POST /auth/login  │  AuthService → JWT (sub = username)          │
   ◄──────────────      │                                             │
       JWT              │                                             │
                        │                                             │
   2. POST /uploads/loan│  get_current_user → decode JWT, load user    │
      Bearer <JWT>      │  require_roles(admin) → RBAC check           │
      file=@sample.csv  │                                             │
   ──────────────►      │  UploadService.upload_and_trigger():         │
                        │   • validate ext / size / sanitize name      │
                        │   • write file → /data/uploads/<uuid>-name   │
                        │   • INSERT file_uploads (status=stored)      │
                        │   • INSERT audit_logs (file.stored)          │
                        │   • _get_department_emails()  ── SELECT ───┐ │
                        │   • WindmillService.trigger_upload_workflow()│
                        └───────────────────┬──────────────────────┼──┘
                                            │ 3. POST jobs/run/f/   │
                                            │    {workflow_path}    │
                                            ▼                       │
                        ┌─────────────────────────────────────────┐ │
                        │           Windmill flow (worker)        │ │
                        │  payload: upload_id, file_path,         │ │
                        │  original_filename, user, ingest_url,   │ │
                        │  ingest_token, department_emails,       │ │
                        │  smtp_config                            │ │
                        │                                         │ │
                        │  • read CSV from /data/uploads (ro)     │ │
                        │  • split rows by department             │ │
                        │  • send emails via smtp_config ─────────┼─┼──► Gmail SMTP
                        │  • POST ingest_url with X-Ingest-Token  │ │
                        └───────────────────┬─────────────────────┘ │
                                            │ 4. POST /internal/ingest│
                                            ▼                       │
                        ┌─────────────────────────────────────────┐ │
                        │             FastAPI api                 │ │
                        │  _verify_ingest_token (X-Ingest-Token)  │ │
                        │  INSERT finance_data / hr_data /        │ │
                        │         sales_data rows                 │ │
                        └───────────────────┬─────────────────────┘ │
                                            ▼                       ▼
                        ┌─────────────────────────────────────────────┐
                        │              PostgreSQL  loan_db             │
                        │  users · file_uploads · audit_logs ·         │
                        │  department_settings · finance/hr/sales_data │
                        └─────────────────────────────────────────────┘
                                            ▲
   5. GET /data/me  ────────────────────────┘  (RBAC: admin = all, dept user = own rows)
```

---

## 3. Phase 0 — Boot / startup

Defined in [app/main.py](app/main.py) `lifespan()`. Runs once when the `api` container starts:

1. `create_database_schema()` — creates all tables (`create_all`; no Alembic yet).
2. `seed_demo_users()` — inserts demo users **only if missing**:
   | username | password | role |
   |---|---|---|
   | `admin` | `admin1234` | `admin` |
   | `finance_user` | `finance1234` | `finance` |
   | `hr_user` | `hr1234` | `hr` |
   | `sales_user` | `sales1234` | `sales` |
3. `seed_department_settings()` — inserts `department_settings` rows from `.env`
   (`FINANCE_EMAIL` / `HR_EMAIL` / `SALES_EMAIL`) **only if the row is missing**.

> ⚠️ Both seed functions **skip rows that already exist** — they never update. See §7.

---

## 4. Phase 1 — Authentication

| Step | Endpoint | What happens |
|---|---|---|
| Register | `POST /api/v1/auth/register` | `AuthService.register()` — hash password, insert `users` row |
| Login | `POST /api/v1/auth/login` | `AuthService.login()` — verify password, return signed JWT |

The JWT carries `sub` (username). On every protected request:
- [app/api/dependencies.py](app/api/dependencies.py) `get_current_user()` decodes the token, reads `sub`,
  then **re-loads the user from PostgreSQL** and checks `is_active`.
- PostgreSQL is the source of truth — the token is never trusted for role/active state.

---

## 5. Phase 2 — Upload & trigger (the core workflow)

Endpoint: `POST /api/v1/uploads/loan` — [app/api/v1/routers/uploads.py](app/api/v1/routers/uploads.py)

1. **RBAC** — `require_roles(Role.admin)` ([app/core/rbac.py](app/core/rbac.py)). Only `admin` can upload loan files. Any other role → `403`.
2. **`UploadService.upload_and_trigger()`** — [app/services/upload_service.py](app/services/upload_service.py):
   - Validate extension against `ALLOWED_UPLOAD_EXTENSIONS` → bad type = `400`.
   - Sanitize filename → store as `/data/uploads/<uuid>-<safe_name><ext>`.
   - Stream file to disk, enforcing `MAX_UPLOAD_BYTES` → too big = `413`.
   - `INSERT file_uploads` with `status = stored`.
   - `INSERT audit_logs` action `file.stored`.
   - `_get_department_emails()` → **`SELECT * FROM department_settings`** (the DB table, *not* `.env`).
   - **`WindmillService.trigger_upload_workflow()`** — [app/services/windmill_service.py](app/services/windmill_service.py):
     - If `WINDMILL_MOCK=true` → returns a fake `mock-<uuid>` job id, no HTTP call.
     - Else `POST {WINDMILL_BASE_URL}/api/w/{WINDMILL_WORKSPACE}/jobs/run/f/{WINDMILL_WORKFLOW_PATH}`
       with `Authorization: Bearer {WINDMILL_TOKEN}` and this JSON payload:
       | Field | Source |
       |---|---|
       | `upload_id`, `file_path`, `original_filename` | the new `file_uploads` row |
       | `user` | caller's username |
       | `ingest_url` | `INGEST_CALLBACK_URL` |
       | `ingest_token` | `INGEST_TOKEN` |
       | `department_emails` | the `department_settings` **table** |
       | `smtp_config` | `SMTP_*` **env vars** |
     - Returns the Windmill job `uuid`.
   - On success → `file_uploads.status = workflow_triggered`, `windmill_job_id` set, audit `workflow.triggered`.
   - On any exception → `file_uploads.status = workflow_failed`, then the error is re-raised.

---

## 6. Phase 3 — Windmill flow → ingest callback

The flow `u/admin/loan_pipeline` runs **inside Windmill** (the worker container). The
[windmill-flow.json](windmill-flow.json) in this repo is only a **stub/template** — the real
logic lives in Windmill's own database and is edited in the UI at `http://localhost:8080`.

A complete flow does:
1. Read the CSV from `file_path` (visible because `upload_data` is mounted into the worker).
2. Split rows into `finance` / `hr` / `sales`.
3. Send a notification email per department using `smtp_config` → `department_emails`.
4. Call back FastAPI: `POST {ingest_url}` with header `X-Ingest-Token: {ingest_token}`.

**Ingest endpoint** — `POST /api/v1/internal/ingest` ([app/api/v1/routers/internal.py](app/api/v1/routers/internal.py)):
- `_verify_ingest_token` — rejects unless `X-Ingest-Token` equals `INGEST_TOKEN` → `401`.
- For each row, inserts into `finance_data` / `hr_data` / `sales_data` (`DEPARTMENT_MODELS`).
- Returns per-department insert counts.

---

## 7. Phase 4 — Reading department data

Endpoint: `GET /api/v1/data/me` and `GET /api/v1/data/{department}` — [app/api/v1/routers/data.py](app/api/v1/routers/data.py)

- `admin` → sees **all** departments combined.
- `finance` / `hr` / `sales` user → sees **only their own** department's rows.
- Mismatched role + department → `403`; unknown department → `404`.

---

## 8. Two config mechanisms — the important gotcha

Not all config reaches the workflow the same way. This is the #1 source of
"I changed `.env` but nothing updated" confusion:

| Config | Path into the workflow | To change it you must... |
|---|---|---|
| `SMTP_*`, `WINDMILL_*`, `INGEST_*` | Read **live from env vars** on every trigger | Edit `.env` **and recreate the container**: `docker compose up -d --force-recreate api` |
| `FINANCE_EMAIL` / `HR_EMAIL` / `SALES_EMAIL` | Only **seed** the `department_settings` table on first boot | `UPDATE department_settings` directly — `.env` is ignored once rows exist |

**Why `.env` edits don't "just work":**
- `docker-compose.yml` `env_file: .env` snapshots `.env` into the container's environment
  **at container-create time**. A running container keeps that frozen snapshot.
- `docker compose restart` reuses the snapshot — it does **not** re-read `.env`.
  Only `--force-recreate` (or `down` + `up`) rebuilds it.
- `pydantic-settings` prefers real env vars over the `.env` file, so even though the
  bind-mounted `/app/.env` is current, the app still reads the frozen snapshot.

**Update department emails on a running system:**
```powershell
docker exec fastapi_windmill_postgres psql -U postgres -d loan_db -c `
  "UPDATE department_settings SET email='new@example.com' WHERE department='finance';"
```

---

## 9. Data model (`loan_db`)

| Table | Written by | Purpose |
|---|---|---|
| `users` | register / `seed_demo_users` | accounts + role + active flag |
| `file_uploads` | `UploadService` | upload metadata, `status`, `windmill_job_id` |
| `audit_logs` | `AuditService` | security/workflow audit trail |
| `department_settings` | `seed_department_settings` (once) | per-department notification email |
| `finance_data` / `hr_data` / `sales_data` | `/internal/ingest` | department-split rows from processed files |

**`file_uploads.status` lifecycle:**
```text
stored ──► workflow_triggered      (Windmill accepted the job)
      └──► workflow_failed         (trigger raised an exception)
```

---

## 10. Endpoint reference

| Method | Path | Auth | Roles |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | none | — |
| `POST` | `/api/v1/auth/login` | none | — |
| `POST` | `/api/v1/uploads/loan` | Bearer JWT | `admin` |
| `POST` | `/api/v1/internal/ingest` | `X-Ingest-Token` | called by Windmill |
| `GET` | `/api/v1/data/me` | Bearer JWT | any (scoped by role) |
| `GET` | `/api/v1/data/{department}` | Bearer JWT | `admin` or matching dept |
| `GET` | `/api/v1/health/live` · `/ready` | none | — |

---

## 11. Quick end-to-end test

```powershell
# 1. Login as the seeded admin
$token = (Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method Post `
  -ContentType 'application/json' `
  -Body '{"username":"admin","password":"admin1234"}').access_token

# 2. Upload a loan file (triggers the Windmill flow)
Invoke-RestMethod -Uri http://localhost:8000/api/v1/uploads/loan -Method Post `
  -Headers @{ Authorization = "Bearer $token" } `
  -Form @{ file = Get-Item .\sample.csv }

# 3. Inspect results
docker exec fastapi_windmill_postgres psql -U postgres -d loan_db -c `
  "SELECT id, status, windmill_job_id FROM file_uploads ORDER BY id DESC LIMIT 3;"

# 4. After the flow's ingest callback, read the department data
Invoke-RestMethod -Uri http://localhost:8000/api/v1/data/me -Method Get `
  -Headers @{ Authorization = "Bearer $token" }
```
