# 🚀 Automatic Pipeline Trigger Guide

## Overview

You can trigger the pipeline **automatically on code push** in two ways:

---

## Option 1: GitHub Actions (Recommended - Standalone) ✅

**What it does:** Runs pipeline automatically when code is pushed to `main` or `develop` branch.

### Setup

1. **GitHub Secrets** (required for email notifications)
   - Go to your GitHub repo → Settings → Secrets and variables → Actions
   - Add these secrets:
     ```
     SMTP_USER     = your-gmail@gmail.com
     SMTP_PASS     = your-app-password
     NOTIFY_EMAIL  = recipient@gmail.com
     ```

2. **Workflow file** (already created)
   - File: `.github/workflows/run-pipeline-on-push.yml`
   - Triggers automatically on push to `main` or `develop`
   - Spins up PostgreSQL, initializes DB, runs pipeline

3. **View results**
   - Go to GitHub repo → Actions tab
   - Click on the workflow run to see logs
   - Download artifacts (pipeline output)

### How it works

```
Developer pushes code
       ↓
GitHub Actions triggered
       ↓
PostgreSQL spins up in container
       ↓
DB initialized from init.sql
       ↓
run_pipeline.py executes
       ↓
Results logged & artifacts saved
```

### Pros & Cons

| Pros | Cons |
|------|------|
| ✅ No external setup needed | ❌ Results not in Windmill UI |
| ✅ Free (GitHub included) | ❌ Separate monitoring |
| ✅ Completely standalone | ❌ Slower (spins up fresh container) |
| ✅ Easy to debug in Actions UI | |

---

## Option 2: Windmill Webhook (Advanced)

**What it does:** Triggers Windmill pipeline when code is pushed.

### Requirements

- Windmill instance running (on Docker)
- Windmill API token
- Webhook secret

### Setup

1. **Get Windmill API details**
   ```
   API URL: http://windmill-instance:8000
   API Token: (create in Windmill UI)
   ```

2. **Create GitHub Actions workflow** (trigger Windmill via API)
   ```yaml
   - name: Trigger Windmill Pipeline
     run: |
       curl -X POST \
         http://windmill-instance:8000/api/v1/jobs/run \
         -H "Authorization: Bearer ${{ secrets.WINDMILL_TOKEN }}" \
         -H "Content-Type: application/json" \
         -d '{"path": "u/admin/run_pipeline"}'
   ```

3. **Results appear in Windmill UI**
   - View in Windmill dashboard
   - Centralized monitoring
   - Better for production

### Pros & Cons

| Pros | Cons |
|------|------|
| ✅ Centralized in Windmill UI | ❌ Requires Windmill running |
| ✅ Better for production | ❌ More complex setup |
| ✅ Unified monitoring | ❌ Extra infrastructure |

---

## Current Configuration

### GitHub Actions Workflow (Recommended)

**File:** `.github/workflows/run-pipeline-on-push.yml`

**Triggered on:**
- Push to `main` or `develop` branch
- Changes in `windmill/scripts/` folder

**What runs:**
1. Checkout code
2. Set up Python 3.11
3. Start PostgreSQL service
4. Run `db/init.sql`
5. Execute `windmill/scripts/run_pipeline.py`
6. Save results as artifact

**Environment variables:**
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=windmill
DB_PASSWORD=windmill123
DB_NAME=windmill_db
```

### Run Locally (Testing)

```bash
# Test the pipeline locally before pushing
cd windmill/scripts
python __main__.py

# Or with custom env vars
export DB_HOST=your-host
export SMTP_USER=your-email@gmail.com
export SMTP_PASS=your-app-password
python __main__.py
```

---

## Next Steps

### 1. Test GitHub Actions

```bash
# 1. Commit and push to main branch
git add .
git commit -m "Add auto-trigger pipeline on push"
git push origin main

# 2. Go to GitHub Actions tab and watch it run
# 3. Check logs if any issues
```

### 2. Configure Email Notifications (Optional)

If you want email alerts:

```bash
# 1. Create Gmail App Password
#    https://support.google.com/accounts/answer/185833

# 2. Add to GitHub Secrets
#    SMTP_USER=your-gmail@gmail.com
#    SMTP_PASS=app-password-from-google
#    NOTIFY_EMAIL=recipient@gmail.com

# 3. Re-run workflow (or push new code)
```

### 3. Monitor & Debug

**GitHub Actions UI:**
- View workflow runs
- See detailed logs
- Download artifacts

**Logs show:**
- Step 1: Rows loaded
- Step 2: Rows filtered
- Step 3: Rows stored
- Step 4: Email sent (if configured)

---

## Troubleshooting

### Workflow fails to run

**Check:**
- Is branch name correct? (must be `main` or `develop`)
- Is the file in correct location? (`.github/workflows/run-pipeline-on-push.yml`)
- Any syntax errors in YAML?

### Database connection fails

**Check:**
- PostgreSQL service started correctly
- `db/init.sql` exists and is valid
- Environment variables correct

### Email not sending

**Check:**
- `SMTP_USER` and `SMTP_PASS` secrets configured?
- Using Gmail App Password (not regular password)?
- `NOTIFY_EMAIL` is valid?

### Pipeline runs but no data

**Check:**
- `table_a` has test data
- Filter conditions (status='active', age>=18)
- Check `pipeline_log` table for errors

---

## Comparison Table

| Feature | GitHub Actions | Windmill UI |
|---------|---|---|
| **Trigger** | On git push (auto) | Manual click (or webhook) |
| **Standalone** | ✅ Yes | ❌ Needs Windmill running |
| **Setup** | Simple | Complex |
| **Monitoring** | GitHub Actions UI | Windmill UI |
| **Cost** | Free | Depends on deployment |
| **Best for** | CI/CD pipeline | Production pipelines |

---

## Current Status

✅ **GitHub Actions workflow ready**
- Automatically triggers on push
- Runs standalone (no Windmill needed)
- Email notifications supported
- Results saved as artifacts

**To activate:**
1. Add GitHub Secrets (for email)
2. Commit and push
3. Watch it run in Actions tab

No additional Windmill configuration needed for this setup.
