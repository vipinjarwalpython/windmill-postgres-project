# Windmill PostgreSQL Pipeline — Modular Docker Project

A beginner-friendly, end-to-end data pipeline using:
- **Python** — one file per pipeline step
- **Docker** — isolated service per step
- **PostgreSQL** — source (table_a) and destination (table_b)
- **Windmill** — workflow UI and job runner
- **GitHub Actions** — CI/CD trigger on git push

---

## Project Structure

```
windmill-postgres-project/
│
├── docker-compose.yml          ← all services defined here
├── .env                        ← DB + email credentials
├── requirements.txt            ← shared Python deps
├── run_pipeline.sh             ← run all 4 steps locally
│
├── db/
│   └── init.sql                ← creates tables + seeds data
│
├── config/
│   └── db.py                   ← shared DB connection helper
│
├── services/
│   ├── load_data/
│   │   ├── Dockerfile
│   │   └── load_data.py        ← STEP 1: read table_a → raw_data.json
│   │
│   ├── process_data/
│   │   ├── Dockerfile
│   │   └── process_data.py     ← STEP 2: filter → processed_data.json
│   │
│   ├── store_data/
│   │   ├── Dockerfile
│   │   └── store_data.py       ← STEP 3: insert into table_b → summary.json
│   │
│   └── notify/
│       ├── Dockerfile
│       └── notify.py           ← STEP 4: send email
│
├── windmill/
│   └── scripts/
│       └── run_pipeline.py     ← Windmill UI script (all 4 steps)
│
└── .github/
    └── workflows/
        └── deploy.yml          ← GitHub Actions CI/CD
```

---

## How Data Flows

```
[table_a in PostgreSQL]
        ↓  load_data.py
[/shared/raw_data.json]
        ↓  process_data.py  (filter: active + age>=18)
[/shared/processed_data.json]
        ↓  store_data.py
[table_b in PostgreSQL] + [/shared/summary.json]
        ↓  notify.py
[Email sent ✅]
```

---

## Local Setup Commands

```bash
# 1. Start Postgres + Windmill
docker compose up -d postgres windmill

# 2. Check DB was seeded
docker exec -it wm_postgres psql -U windmill -d windmill_db \
  -c "SELECT * FROM table_a;"

# 3. Run full pipeline (all 4 steps)
chmod +x run_pipeline.sh
./run_pipeline.sh

# 4. Verify result
docker exec -it wm_postgres psql -U windmill -d windmill_db \
  -c "SELECT * FROM table_b;"

# 5. Check pipeline logs
docker exec -it wm_postgres psql -U windmill -d windmill_db \
  -c "SELECT * FROM pipeline_log;"
```

---

## Run Steps Individually

```bash
# Step 1 only
docker compose run --rm load_data

# Step 2 only
docker compose run --rm process_data

# Step 3 only
docker compose run --rm store_data

# Step 4 only
docker compose run --rm notify
```

---

## Windmill UI

```
Open: http://localhost:8000
Login: admin@windmill.dev / changeme
```

1. Resources → Add Resource → postgresql → fill DB details
2. Scripts → New Script → Python → paste windmill/scripts/run_pipeline.py
3. Run script → pass db resource + email

---

## GitHub Secrets Needed

| Secret | Value |
|---|---|
| WINDMILL_TOKEN | From Windmill UI → Settings → Tokens |
| WINDMILL_WORKSPACE | your workspace slug |
| WINDMILL_BASE_URL | http://YOUR_SERVER:8000 |
| EMAIL_USER | your@gmail.com |
| EMAIL_PASS | Gmail App Password |
| NOTIFY_EMAIL | notify@example.com |
