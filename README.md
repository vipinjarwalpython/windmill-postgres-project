# Loan Pipeline — FastAPI + Windmill + PostgreSQL

A small but real backend that lets a logged-in user upload a CSV file, automatically processes it
in the background, splits the rows by department (finance / HR / sales), emails each team, and
saves the data to a database — so every team only sees their own rows.

If you've never touched FastAPI, Docker, or Windmill before, this README is written for you.
Follow it top-to-bottom and you'll have the whole thing running on your computer in ~10 minutes.

---

## What is this project? (in plain English)

Imagine a manager uploads a single big CSV with rows for finance, HR, and sales mixed together.
This project does the following automatically:

1. **You log in** to a small website (`http://localhost:8000`).
2. **You upload the CSV.** The backend (FastAPI) saves the file safely.
3. **A workflow tool called Windmill takes over** in the background. It reads the CSV,
   splits the rows by department, and emails each team their part.
4. **Windmill calls back** to the backend and saves the split rows into a database.
5. **Each user only sees their own data** when they log in. Admin sees everything.

That's it. The clever bits are **security** (only the right person can upload), **automation**
(Windmill does the boring work), and **clean separation** (each team only sees their rows).

---

## What you need installed (one time)

| Tool | Why | How to check |
|---|---|---|
| **Docker Desktop** | Runs the whole project in containers so you don't install Python/Postgres yourself | `docker --version` |
| **Git** | To download (clone) the project | `git --version` |
| **A web browser** | To use the app and read API docs | Already installed |

That's all. No Python, no Postgres, no Node — Docker handles everything.

If you don't have Docker: download it free from <https://www.docker.com/products/docker-desktop>
and start it (you'll see a whale icon in your taskbar when it's running).

---

## Quick start (5 commands, ~10 minutes)

Open PowerShell in the project folder and run:

```powershell
# 1. Copy the example settings file to a real one (only needed once)
Copy-Item .env.example .env

# 2. Build and start everything (FastAPI + Postgres + Windmill). The first run downloads ~1GB of images.
docker compose up --build -d

# 3. Check that all containers are healthy (you should see "Up" or "healthy" next to each)
docker compose ps

# 4. Open the app in your browser
start http://localhost:8000

# 5. (Optional) Open Windmill's UI to see the workflow engine
start http://localhost:8080
```

**Login with the seeded admin account:**

- Username: `admin`
- Password: `admin1234`

That's it — you're running. The next sections explain what just happened and how to use it.

---

## What each command actually did

### `Copy-Item .env.example .env`
Made a copy of the settings template. The `.env` file holds passwords, database URLs, and
email credentials. It's gitignored so your secrets never leave your machine.

### `docker compose up --build -d`
- `docker compose` reads [docker-compose.yml](docker-compose.yml) — the recipe for the whole stack.
- `up` starts the services. `--build` rebuilds the FastAPI image if the code changed.
- `-d` means "detached" — runs in the background so you get your terminal back.

It starts 4 containers:

| Container | What it does | Port |
|---|---|---|
| `fastapi_windmill_api` | The FastAPI backend (Python) | <http://localhost:8000> |
| `fastapi_windmill_postgres` | The PostgreSQL database | `localhost:5432` |
| `windmill_server` | Windmill's web UI and API | <http://localhost:8080> |
| `windmill_worker` | Runs the actual workflow jobs | (internal) |

### `docker compose ps`
Lists the running containers. Look for `healthy` or `Up` in the status column.
If anything says `Exited` or `Restarting`, check the logs (see Troubleshooting below).

---

## Everyday commands (cheat sheet)

```powershell
# Start everything (after first build)
docker compose up -d

# Stop everything (data is kept)
docker compose down

# Stop everything AND delete data (fresh start — careful!)
docker compose down -v

# See live logs from the API
docker compose logs -f api

# See live logs from Windmill
docker compose logs -f windmill_server windmill_worker

# Restart just the API (after editing code — but with volume mount, hot-reload usually works)
docker compose restart api

# Apply changes from .env (restart alone is NOT enough — you must recreate the container)
docker compose up -d --force-recreate api

# Open a database shell
docker exec -it fastapi_windmill_postgres psql -U postgres -d loan_db
```

> **Tip:** Whenever you edit `.env`, you must run `docker compose up -d --force-recreate api`.
> A plain `restart` keeps the old environment values cached. See [WORKFLOW.md](WORKFLOW.md) section 8.

---

## Try it end-to-end (3 ways)

### Option A — The browser (easiest)

1. Go to <http://localhost:8000>. You'll land on the login page.
2. Log in as `admin` / `admin1234`.
3. Click **Uploads** in the sidebar.
4. Click **Choose file**, pick [sample.csv](sample.csv) from the project root, and submit.
5. Click **Dashboard** to see the upload appear with status `workflow_triggered`.
6. Open <http://localhost:8080> (Windmill) — you'll see a job running. When it finishes,
   go back to the dashboard and you'll see department rows appear.

### Option B — The interactive API docs

1. Open <http://localhost:8000/docs>. This is Swagger UI — auto-generated docs for every endpoint.
2. Click **POST /api/v1/auth/login** → **Try it out** → paste:
   ```json
   { "username": "admin", "password": "admin1234" }
   ```
   Click **Execute**. Copy the `access_token` from the response.
3. Click the green **Authorize** button at the top right, paste the token, and click **Authorize**.
4. Now scroll to **POST /api/v1/uploads/loan** → **Try it out** → choose `sample.csv` → **Execute**.

### Option C — PowerShell (most reproducible)

```powershell
# 1. Log in and capture the token in a variable
$token = (Invoke-RestMethod -Uri http://localhost:8000/api/v1/auth/login -Method Post `
  -ContentType 'application/json' `
  -Body '{"username":"admin","password":"admin1234"}').access_token

# 2. Upload a CSV (this triggers Windmill in the background)
Invoke-RestMethod -Uri http://localhost:8000/api/v1/uploads/loan -Method Post `
  -Headers @{ Authorization = "Bearer $token" } `
  -Form @{ file = Get-Item .\sample.csv }

# 3. Look at the most recent uploads in the database
docker exec fastapi_windmill_postgres psql -U postgres -d loan_db -c `
  "SELECT id, original_filename, status, windmill_job_id FROM file_uploads ORDER BY id DESC LIMIT 3;"

# 4. After ~5 seconds, fetch the split data the Windmill flow saved back
Invoke-RestMethod -Uri http://localhost:8000/api/v1/data/me -Method Get `
  -Headers @{ Authorization = "Bearer $token" }
```

---

## Who can do what? (RBAC)

The app ships with 4 demo users (seeded automatically on first start):

| Username | Password | Role | Can do |
|---|---|---|---|
| `admin` | `admin1234` | admin | Everything — upload files, see all departments |
| `finance_user` | `finance1234` | finance | See only the **finance** rows |
| `hr_user` | `hr1234` | hr | See only the **HR** rows |
| `sales_user` | `sales1234` | sales | See only the **sales** rows |

Try logging in as `finance_user` and you'll notice the **Uploads** page is forbidden — only
`admin` can upload. That's RBAC (Role-Based Access Control) in action.

---

## The API at a glance

| What | Method + URL | Who can call it |
|---|---|---|
| Register a new user | `POST /api/v1/auth/register` | Anyone |
| Log in (get a JWT token) | `POST /api/v1/auth/login` | Anyone |
| Upload a CSV | `POST /api/v1/uploads/loan` | `admin` only |
| See my department data | `GET /api/v1/data/me` | Any logged-in user |
| See a specific department | `GET /api/v1/data/{finance\|hr\|sales}` | `admin` or matching dept user |
| Health check | `GET /api/v1/health/ready` | Anyone |

Full interactive docs: <http://localhost:8000/docs>

---

## Project structure (what lives where)

```text
fastapi-windmill-rbac/
├── app/                              ← the FastAPI backend (Python)
│   ├── main.py                       ← app startup: middleware, routes, DB seeding
│   ├── api/v1/routers/               ← API endpoints (auth, uploads, data, internal)
│   ├── core/                         ← config, JWT, RBAC, logging
│   ├── db/                           ← database connection + seed data
│   ├── models/                       ← SQLAlchemy table definitions
│   ├── schemas/                      ← Pydantic request/response shapes
│   ├── services/                     ← business logic (auth, upload, Windmill client)
│   ├── templates/                    ← HTML pages (login, dashboard, uploads)
│   ├── static/                       ← CSS + JS for the dashboard
│   └── web/                          ← the browser-facing routes
├── docker-entrypoint-initdb.d/       ← SQL run once when Postgres first starts
├── docker-compose.yml                ← the recipe for all 4 containers
├── Dockerfile                        ← how to build the FastAPI image
├── requirements.txt                  ← Python packages
├── .env.example                      ← copy this to .env and edit
├── sample.csv                        ← test file you can upload
├── windmill-flow.json                ← the Windmill workflow definition
├── windmill-app-dashboard.json       ← a ready-made Windmill dashboard UI
├── install-dashboard.ps1             ← installs that dashboard into Windmill
├── postman_collection.json           ← import into Postman to test the API
└── WORKFLOW.md                       ← deep dive: how everything connects
```

---

## What's Windmill and why is it here?

[Windmill](https://www.windmill.dev/) is an open-source workflow engine. Think of it as a
"if-this-then-that for developers" — you define a flow (a series of steps), and Windmill runs it
reliably, retries on failure, logs everything, and gives you a UI to inspect runs.

**Why we use it:** FastAPI shouldn't get bogged down processing files. Instead, FastAPI just
**triggers** a Windmill flow and immediately returns to the user. Windmill does the slow work
(reading the CSV, splitting rows, sending emails) in the background.

**Where the flow lives:** the actual flow runs **inside Windmill's database** (you edit it in the
Windmill UI at <http://localhost:8080>). The [windmill-flow.json](windmill-flow.json) file in this
repo is a starter template you can import.

**For the full deep-dive on the FastAPI ↔ Windmill connection**, including how to push your flow
to Windmill, how the callback works, and the gotchas around `.env` changes, **read
[WORKFLOW.md](WORKFLOW.md)**.

---

## Common problems and fixes

| Problem | Likely cause | Fix |
|---|---|---|
| `port 8000 already in use` | Something else is using port 8000 | Stop the other thing, or change the port in `docker-compose.yml` |
| `docker compose: command not found` | Docker Desktop isn't installed / running | Install Docker Desktop and start it |
| `docker compose up` hangs at `=> [api] load build context` | OneDrive interfering with BuildKit on Windows | Run `.\docker-compose-classic.ps1 up --build -d` instead |
| Login fails with "invalid credentials" | DB volume was deleted but app hasn't reseeded | `docker compose restart api` — the lifespan hook reseeds on startup |
| Upload returns 403 | You're logged in as a non-admin | Log in as `admin` |
| Upload returns 413 | File bigger than `MAX_UPLOAD_BYTES` (10 MB by default) | Use a smaller file or raise the limit in `.env` |
| Windmill job stays `triggered` and never finishes | Worker isn't running or flow isn't imported | `docker compose ps` then check `windmill_worker` logs |
| Changed `.env` but nothing updated | Restart doesn't re-read `.env` | `docker compose up -d --force-recreate api` |
| Emails never arrive | SMTP credentials wrong or Gmail blocked the app | Use a [Gmail App Password](https://myaccount.google.com/apppasswords) in `SMTP_PASSWORD` |
| `psql: database "loan_db" does not exist` | Postgres still booting | Wait 10s, the healthcheck takes a moment |

When stuck, always look at the logs first:

```powershell
docker compose logs -f api          # FastAPI errors
docker compose logs -f windmill_worker   # workflow errors
```

---

## Want to keep going?

- **[WORKFLOW.md](WORKFLOW.md)** — the full end-to-end story: how FastAPI and Windmill talk to
  each other, how to push/pull flows, how the ingest callback works, and every config knob.
- **Windmill docs** — <https://www.windmill.dev/docs/intro>
- **FastAPI docs** — <https://fastapi.tiangolo.com/>
- **Postman collection** — import [postman_collection.json](postman_collection.json) into
  Postman to play with the API outside the browser.

---

## Stop everything when you're done

```powershell
docker compose down
```

This stops all containers but **keeps your data** (uploads + database). To wipe everything and
start fresh:

```powershell
docker compose down -v
```

The `-v` deletes the volumes — gone for good. Good for a clean test, bad if you have real data.
