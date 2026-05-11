# 🎯 Windmill UI - Auto-Trigger Guide

## Setup Overview

When you push code to GitHub, it **automatically triggers your Windmill pipeline** and results appear in **Windmill UI dashboard**.

```
Developer pushes code
       ↓
GitHub Actions triggered
       ↓
Calls Windmill API
       ↓
Pipeline runs in Windmill UI
       ↓
Results visible in Windmill dashboard
```

---

## Step-by-Step Setup

### **Step 1: Get Windmill URL**

Your Windmill instance URL (from your docker-compose):

```
Local:       http://localhost:8000
Production:  https://your-windmill-domain.com
```

**Keep this URL handy** — you'll need it for GitHub Secrets.

---

### **Step 2: Create Windmill API Token**

1. **Log into Windmill UI** (http://localhost:8000)
2. Click **Settings** (gear icon, bottom left)
3. Go to **Tokens** tab
4. Click **Create new token**
5. Name it: `github-auto-trigger`
6. Scopes needed:
   - ✅ `jobs:run` (to trigger jobs)
   - ✅ `scripts:read` (to read script metadata)
7. Copy the token (starts with `wk_`)
8. **Save it somewhere safe** — you won't see it again

---

### **Step 3: Add GitHub Secrets**

Go to GitHub repo → **Settings** → **Secrets and variables** → **Actions**

Add these secrets:

```
Name:  WINDMILL_URL
Value: http://localhost:8000
       (or your production Windmill URL)

Name:  WINDMILL_TOKEN
Value: wk_xxxxxxxxxxxxxxxxxxxx
       (from Step 2)

Name:  DB_HOST
Value: postgres

Name:  DB_PORT
Value: 5432

Name:  DB_USER
Value: windmill

Name:  DB_PASSWORD
Value: windmill123

Name:  DB_NAME
Value: windmill_db

Name:  SMTP_USER
Value: your-email@gmail.com

Name:  SMTP_PASS
Value: your-gmail-app-password

Name:  NOTIFY_EMAIL
Value: recipient@example.com
```

---

### **Step 4: Verify Pipeline Script in Windmill**

Make sure your `run_pipeline.py` is uploaded to Windmill:

1. In Windmill UI, go to **Scripts** → **Create Script**
2. Paste contents of `windmill/scripts/run_pipeline.py`
3. Set path to: `u/admin/run_pipeline`
4. Save and run once manually to test
5. Check the **Inputs** section shows your parameters:
   ```
   ✓ db_host (string)
   ✓ db_port (integer)
   ✓ db_user (string)
   ✓ db_password (string)
   ✓ db_name (string)
   ✓ smtp_user (string)
   ✓ smtp_pass (string)
   ✓ notify_email (string)
   ```

---

### **Step 5: Commit & Push**

```bash
git add .github/workflows/trigger-windmill.yml
git commit -m "Add Windmill auto-trigger on code push"
git push origin main
```

---

## What Happens Next

### **On Every Push:**

1. GitHub Actions workflow `trigger-windmill.yml` runs
2. Calls Windmill API: `POST /api/v1/jobs/run`
3. Pipeline executes in Windmill
4. Results appear in **Windmill UI** → Jobs tab
5. Email notification sent (if configured)

### **View Results:**

1. Go to **Windmill UI** (http://localhost:8000)
2. Click **Jobs** (left sidebar)
3. You'll see:
   - Job status (running/completed/failed)
   - Start time & duration
   - Step-by-step logs
   - Data processed

---

## Monitoring in Windmill UI

### **Dashboard Shows:**

```
Job ID:      1f329a-xxxxx
Status:      ✅ Completed
Duration:    2.5s
Triggered:   GitHub Actions
Result:      {
               "status": "success",
               "rows_loaded": 10,
               "rows_filtered": 5,
               "rows_stored": 5,
               "timestamp": "2024-05-11 15:30:45"
             }
Logs:        [Step 1] Load Data
             ✅ Loaded 10 rows
             [Step 2] Process Data
             ✅ Filtered: 10 → 5 rows
             [Step 3] Store Data
             ✅ Stored 5 rows into table_b
             [Step 4] Notify
             ✅ Email sent to recipient@gmail.com
```

---

## Troubleshooting

### **"Failed to trigger pipeline"**

Check:
- ✅ WINDMILL_URL is correct? (with http:// or https://)
- ✅ WINDMILL_TOKEN is valid? (should start with `wk_`)
- ✅ Token has `jobs:run` scope?
- ✅ Windmill is running and accessible from GitHub?

### **"Script not found: u/admin/run_pipeline"**

Check:
- ✅ Script uploaded to Windmill at path `u/admin/run_pipeline`
- ✅ Path exactly matches in workflow file
- ✅ Script has correct input parameters

### **"Invalid arguments"**

Check:
- ✅ All parameters have correct types (db_port must be integer, not string)
- ✅ Parameters match function signature in `run_pipeline.py`

### **Job created but didn't run**

Check:
- ✅ Windmill has database access
- ✅ DB credentials are correct
- ✅ Check Windmill logs for errors

---

## Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `WINDMILL_URL` | Your Windmill instance | `http://localhost:8000` |
| `WINDMILL_TOKEN` | API auth token | `wk_xxxx...` |
| `DB_HOST` | Database host | `postgres` |
| `DB_PORT` | Database port | `5432` |
| `DB_USER` | Database user | `windmill` |
| `DB_PASSWORD` | Database password | `windmill123` |
| `DB_NAME` | Database name | `windmill_db` |
| `SMTP_USER` | Gmail address | `your@gmail.com` |
| `SMTP_PASS` | Gmail app password | `xxxx xxxx xxxx xxxx` |
| `NOTIFY_EMAIL` | Email recipient | `recipient@example.com` |

---

## How the API Call Works

```bash
POST https://windmill.example.com/api/v1/jobs/run
Authorization: Bearer wk_xxxxxxxxxxxxxxxxxxxx
Content-Type: application/json

{
  "path": "u/admin/run_pipeline",
  "args": {
    "db_host": "postgres",
    "db_port": 5432,
    "db_user": "windmill",
    "db_password": "windmill123",
    "db_name": "windmill_db",
    "smtp_user": "your@gmail.com",
    "smtp_pass": "app-password",
    "notify_email": "recipient@example.com"
  }
}
```

Response:
```json
{
  "id": "1f329a-6573-c85a-b898-2217a08a2e5f",
  "path": "u/admin/run_pipeline",
  "status": "running"
}
```

---

## Workflow File

**Location:** `.github/workflows/trigger-windmill.yml`

**Triggers on:**
- Push to `main` or `develop`
- Changes in `windmill/scripts/` or workflow file itself

**What it does:**
1. Calls Windmill API with parameters
2. Extracts Job ID from response
3. Reports success/failure to GitHub
4. Provides link to Windmill UI

---

## ✨ You're Set Up!

From now on, every code push automatically:
- ✅ Triggers Windmill pipeline
- ✅ Runs in Windmill UI
- ✅ Results visible in dashboard
- ✅ Email notifications sent
- ✅ All logged centrally

**Next time you push:**
```bash
git push origin main
```

Then check **Windmill UI** → **Jobs** to see it running! 🚀
