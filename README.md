# FastAPI + PostgreSQL + Windmill RBAC

Production-style backend for secure file uploads that trigger Windmill workflows.

## Architecture

```text
React/Next.js/curl
  |
  | 1. POST /api/v1/auth/login
  v
FastAPI API
  |
  | JWT contains sub, user_id, role, exp
  v
RBAC dependency
  |
  | 2. POST /api/v1/uploads/loan with Bearer token
  v
Upload service
  |
  | validate extension, size, filename
  | store file in /data/uploads
  | insert file_uploads + audit_logs
  v
Windmill service
  |
  | POST /api/w/{workspace}/jobs/run/f/{flow_path}
  v
Windmill workflow
  |
  | process file, call back API or write output
  v
PostgreSQL
```

## Folder Structure

```text
app/
  main.py                         FastAPI app factory, middleware, routers, startup schema creation
  api/
    dependencies.py               JWT authentication dependency
    v1/router.py                  Versioned API router
    v1/routers/auth.py            Register/login endpoints
    v1/routers/health.py          Liveness/readiness checks
    v1/routers/uploads.py         RBAC-protected upload endpoint
  core/
    config.py                     Environment variable parsing
    logging.py                    JSON structured logging
    rbac.py                       Role-based dependency factory
    security.py                   Password hashing and JWT encode/decode
  db/session.py                   Async SQLAlchemy engine/session
  middleware/
    exception_handler.py          Validation and unhandled error responses
    request_id.py                 Request correlation ID middleware
  models/
    user.py                       User and Role table model
    file_upload.py                Upload metadata and workflow status model
    audit_log.py                  Audit trail table model
  repositories/
    user_repository.py            User database access
  schemas/
    auth.py                       Auth request/response models
    upload.py                     Upload response model
  services/
    auth_service.py               Register/login business logic
    upload_service.py             File validation/storage/workflow trigger
    windmill_service.py           Windmill API client, with local mock mode
```

Root files:

```text
Dockerfile                       Optimized Python image with healthcheck
docker-compose.yml               API + PostgreSQL local stack
requirements.txt                 Pinned Python dependencies
.env.example                     Safe template for environment variables
.env                             Local secrets, do not commit
.dockerignore                    Keeps secrets/cache/uploads out of image builds
docker-compose-classic.ps1       Windows helper when OneDrive + BuildKit has issues
```

## Request Lifecycle

1. User registers with `username`, `password`, and `role`.
2. User logs in and receives a signed JWT.
3. User uploads a file with `Authorization: Bearer <token>`.
4. `get_current_user` decodes the JWT and loads the user from PostgreSQL.
5. `require_roles(Role.admin, Role.loan_officer)` checks permissions.
6. `UploadService` validates extension and max size, sanitizes the filename, writes the file, and stores metadata.
7. `WindmillService` triggers the configured Windmill flow.
8. Upload status becomes `workflow_triggered` or `workflow_failed`.
9. Audit logs record registration, login, storage, and workflow trigger events.

## RBAC and JWT

JWT protects API requests. PostgreSQL remains the source of truth, so every token is decoded and then checked against the current user record. RBAC is enforced through FastAPI dependencies:

```python
Depends(require_roles(Role.admin, Role.loan_officer))
```

Roles:

- `admin`: full upload permission and future admin operations.
- `loan_officer`: can upload loan files.
- `auditor`: intended for read-only audit/reporting endpoints.

## Docker Architecture

- `api`: FastAPI app served by Uvicorn on port `8000`.
- `db`: PostgreSQL 16 on port `5432`.
- `postgres_data`: persistent database volume.
- `upload_data`: persistent uploaded file volume.
- `backend`: private Docker network so `api` reaches PostgreSQL at host `db`.

Important commands:

```powershell
docker compose up --build
```

Builds the API image and starts API + PostgreSQL in the foreground.

```powershell
docker compose up --build -d
```

Same build/start, but detached in the background.

```powershell
docker compose down
```

Stops and removes containers and the network. Volumes remain unless you add `-v`.

```powershell
docker ps
```

Lists running containers and published ports.

```powershell
docker logs fastapi_windmill_api
```

Shows API logs.

```powershell
docker exec -it fastapi_windmill_postgres psql -U postgres -d loan_db
```

Opens PostgreSQL inside the database container.

## Local Setup

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Open:

```text
http://localhost:8000/docs
http://localhost:8000/api/v1/health/ready
```

If Docker BuildKit fails from OneDrive on Windows:

```powershell
.\docker-compose-classic.ps1 up --build -d
```

## API Endpoints

### Register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"alice\",\"password\":\"StrongPass123\",\"role\":\"loan_officer\"}"
```

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"alice\",\"password\":\"StrongPass123\"}"
```

### Upload Loan File

```bash
curl -X POST http://localhost:8000/api/v1/uploads/loan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample.csv"
```

### Health

```bash
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

## Local Windmill + ngrok Integration

This project can run a real local Windmill server in Docker:

```text
FastAPI container          http://localhost:8000
Shared PostgreSQL          localhost:5432
  - FastAPI database       loan_db
  - Windmill database      windmill
Windmill UI/API           http://localhost:8080
ngrok inspector           http://localhost:4040
```

FastAPI calls Windmill through the Docker network:

```env
WINDMILL_BASE_URL=http://windmill_server:8000
WINDMILL_MOCK=false
```

ngrok exposes Windmill to the public internet. Add your token to `.env`:

```env
NGROK_AUTHTOKEN=your-ngrok-authtoken
```

Start local API + PostgreSQL + Windmill:

```powershell
.\docker-compose-classic.ps1 up --build -d
```

Start with the ngrok tunnel too:

```powershell
docker compose --profile tunnel up -d ngrok_windmill
```

Find the public ngrok URL:

```powershell
docker compose logs ngrok_windmill
```

or open:

```text
http://localhost:4040
```

Then update `.env`:

```env
WINDMILL_PUBLIC_URL=https://your-ngrok-url.ngrok-free.app
```

and restart Windmill:

```powershell
docker compose restart windmill_server
```

Open Windmill:

```text
http://localhost:8080
```

Create/import your flow, generate a Windmill token, then update:

```env
WINDMILL_WORKSPACE=your_workspace
WINDMILL_TOKEN=your_windmill_token
WINDMILL_WORKFLOW_PATH=u/admin/loan_pipeline
```

For real Windmill:

```env
WINDMILL_MOCK=false
WINDMILL_BASE_URL=http://windmill_server:8000
WINDMILL_WORKSPACE=prod
WINDMILL_TOKEN=wm_xxxxx
WINDMILL_WORKFLOW_PATH=u/admin/loan_pipeline
```

Users never receive `WINDMILL_TOKEN`. They call FastAPI, FastAPI checks JWT + RBAC, and only the backend triggers Windmill with a service token.

## PostgreSQL

The app uses async SQLAlchemy with `asyncpg`.

Tables:

- `users`: username, password hash, role, active flag.
- `file_uploads`: file metadata, storage path, status, Windmill job ID.
- `audit_logs`: security and workflow audit trail.

For production, replace startup `create_all` with Alembic migrations.

## Security Best Practices

- Use a long random `SECRET_KEY`.
- Store `.env` in a secrets manager in production.
- Keep Windmill token server-side only.
- Use HTTPS behind a reverse proxy or load balancer.
- Restrict CORS to real frontend origins.
- Validate file extension, size, and sanitized names.
- Add virus scanning for untrusted files in production.
- Use short-lived JWTs and refresh tokens if needed.
- Give Windmill service tokens least privilege.
- Log audits without storing raw secrets or passwords.

## Production Deployment

Common layouts:

- VPS: Nginx/Caddy reverse proxy + Docker Compose + managed backups.
- AWS: ECS/Fargate or EKS, RDS PostgreSQL, Secrets Manager, ALB, S3 for file storage.
- Azure: Container Apps/AKS, Azure Database for PostgreSQL, Key Vault, Blob Storage.
- GCP: Cloud Run/GKE, Cloud SQL PostgreSQL, Secret Manager, Cloud Storage.
- Kubernetes: Deployment, Service, Ingress, ConfigMap, Secret, PVC/object storage, HPA.
- Docker Swarm: replicated API service, external PostgreSQL, reverse proxy.

Scale horizontally by making API containers stateless. Move uploads to S3/Azure Blob/GCS, use managed PostgreSQL, and let Windmill handle long-running workflow execution.

## Enterprise Patterns

- Event-driven: upload creates an event consumed by workflow workers.
- Queues: use Redis/RabbitMQ/SQS between API and workflows for retries.
- Webhooks: Windmill can call back FastAPI when processing completes.
- Workflow orchestration: Windmill owns multi-step jobs, retries, and approvals.
- Microservices: keep auth/upload API separate from processing services.

## Frontend Connection

React or Next.js flow:

1. Login form calls `/api/v1/auth/login`.
2. Store access token in memory or secure httpOnly cookie.
3. Upload UI sends `FormData` to `/api/v1/uploads/loan`.
4. Show returned `upload_id`, `status`, and `windmill_job_id`.
5. Poll a status endpoint or receive webhook-driven updates when added.

Avoid localStorage for high-risk apps. Prefer secure, SameSite, httpOnly cookies with CSRF protection.

## Troubleshooting

- Docker networking: inside containers use `db:5432`, not `localhost:5432`.
- PostgreSQL connection refused: wait for healthcheck, verify `DATABASE_URL`.
- Password auth failed: recreate volume after changing DB password with `docker compose down -v`.
- Windmill 401/403: token is missing, expired, or lacks workspace/flow permission.
- Windmill 404: check workspace and flow path.
- JWT invalid: verify `SECRET_KEY`, `ALGORITHM`, and token expiration.
- Upload 413: file exceeds `MAX_UPLOAD_BYTES`.
- Upload 400: extension not in `ALLOWED_UPLOAD_EXTENSIONS`.
- Windows paths: prefer Docker volumes over bind-mounting upload directories.
- OneDrive issues: move repo outside OneDrive or use `docker-compose-classic.ps1`.
- ghcr.io connectivity: login with `docker login ghcr.io`, retry DNS/VPN, or mirror images.
- Volume confusion: `docker compose down -v` deletes database/upload volumes.

## Production Checklist

- Replace local secret values.
- Disable `WINDMILL_MOCK`.
- Add Alembic migrations.
- Use managed PostgreSQL with backups and TLS.
- Use object storage instead of container-local files.
- Add malware scanning for uploads.
- Add rate limiting and request size limits at reverse proxy.
- Add observability: metrics, traces, centralized logs.
- Add CI tests and image scanning.
- Run multiple API replicas behind a load balancer.
