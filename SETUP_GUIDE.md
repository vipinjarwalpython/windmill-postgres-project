# 🚀 Windmill PostgreSQL Pipeline — Complete Setup Guide

**What you'll build:** A data pipeline that filters employees from PostgreSQL and runs automatically via Windmill UI.

---

## 📦 What's Inside This Zip

```
windmill-postgres-project/
├── SETUP_GUIDE.md          ← YOU ARE HERE
├── .env                    ← Edit your email credentials
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── run_pipeline.sh
│
├── config/
│   ├── __init__.py
│   └── db.py               ← Shared DB helper
│
├── db/
│   └── init.sql            ← Creates tables + 10 test rows
│
├── services/
│   ├── load_data/          ← Step 1: Read table_a
│   ├── process_data/       ← Step 2: Filter rows
│   ├── store_data/         ← Step 3: Write table_b
│   └── notify/             ← Step 4: Send email
│
├── windmill/
│   └── scripts/
│       └── run_pipeline.py ← Windmill UI script
│
└── .github/
    └── workflows/
        └── deploy.yml      ← GitHub Actions CI/CD
```

---

## ✅ Prerequisites

Before starting, make sure you have:
- ✅ Docker installed (`docker --version`)
- ✅ Docker Compose installed (`docker compose version`)
- ✅ Git installed (`git --version`)

---

## 🟢 STEP 1 — Start PostgreSQL + Windmill

Open terminal in the project folder and run:

```bash
docker compose up -d postgres windmill
```

Wait 30 seconds, then verify both are running:

```bash
docker ps
```

You should see:
```
wm_postgres    Up (healthy)
windmill       Up
```

---

## 🟢 STEP 2 — Check Database is Ready

```bash
docker exec -it wm_postgres psql -U windmill -d windmill_db \
  -c "SELECT * FROM table_a;"
```

You should see **10 employees** printed:

```
 id |  name   | age |  status  | department  |  salary
----+---------+-----+----------+-------------+---------
  1 | Alice   |  28 | active   | Engineering | 75000
  2 | Bob     |  17 | inactive | Intern      | 15000
  3 | Charlie |  35 | active   | Engineering | 90000
...
```

✅ If you see this, your database is ready!

---

## 🟢 STEP 3 — Open Windmill UI

Open browser: **http://localhost:8000**

Login with:
- Email: `admin@windmill.dev`
- Password: `changeme`

You should see the Windmill dashboard.

---

## 🟢 STEP 4 — Add PostgreSQL Resource in Windmill

This tells Windmill how to connect to your database.

1. In Windmill, click **Resources** (left menu)
2. Click **+ Add Resource**
3. Select type: `postgresql`
4. Fill in:
   ```
   Name:     my_postgres
   Host:     postgres          ← container name, not localhost!
   Port:     5432
   User:     windmill
   Password: windmill123
   Database: windmill_db
   ```
5. Click **Save**

✅ You now have a database connection!

---

## 🟢 STEP 5 — Create Script in Windmill UI

1. Click **Scripts** (left menu)
2. Click **+ New Script**
3. Select language: **Python**
4. In the editor, **delete everything** and paste:

```python
# Copy the ENTIRE content from:
# windmill/scripts/run_pipeline.py
```

Open `windmill/scripts/run_pipeline.py` in this zip and copy ALL of it.

5. Click **Save** (top right)
6. Give it a path: `u/admin/run_pipeline`

---

## 🟢 STEP 6 — Run the Pipeline in Windmill UI

You should now see the script page with a **Run** button.

1. Click **Run**
2. Fill in the parameters:
   ```
   db:           Select "my_postgres" (the resource you created)
   smtp_user:    your@gmail.com (or leave empty to skip email)
   smtp_pass:    your_gmail_app_password (or leave empty)
   notify_email: destination@gmail.com (or leave empty)
   ```
3. Click **Run**

You'll see:
- ✅ Live logs showing all 4 steps
- ✅ Progress: load → process → store → notify
- ✅ Final result showing rows stored

---

## 🟢 STEP 7 — Verify Results

Check that data is in `table_b`:

```bash
docker exec -it wm_postgres psql -U windmill -d windmill_db \
  -c "SELECT * FROM table_b;"
```

You should see **6 filtered employees** (only active + age ≥ 18):

```
 id |  name   | age | status | department  | salary
----+---------+-----+--------+-------------+--------
  1 | Alice   |  28 | active | Engineering | 75000
  2 | Charlie |  35 | active | Engineering | 90000
  3 | Frank   |  30 | active | Marketing   | 65000
  4 | Grace   |  26 | active | Engineering | 80000
  5 | Ivy     |  33 | active | Finance     | 70000
  6 | Jack    |  45 | active | Engineering | 95000
```

✅ **Pipeline works!**

---

## 🟢 STEP 8 — See Job History in Windmill

1. In Windmill UI, click **Runs** (left menu)
2. You'll see your job listed with:
   - ✅ Status (Success)
   - ✅ Duration
   - ✅ Timestamp
3. Click on it to see full logs

---

## 🟢 STEP 9 (Optional) — Run Via Terminal

If you want to run the pipeline **without Windmill UI**:

```bash
# Make script executable
chmod +x run_pipeline.sh

# Run all 4 steps
./run_pipeline.sh
```

This runs the Docker services directly (won't show in Windmill UI).

---

## 🟢 STEP 10 — Push to GitHub (Auto-Deploy)

### A. Create GitHub Repository

1. Go to https://github.com/new
2. Name: `windmill-postgres-project`
3. **Don't** initialize with README
4. Click **Create repository**

### B. Push Your Code

```bash
cd windmill-postgres-project

# Initialize git (if not done)
git init

# Add all files
git add .

# First commit
git commit -m "Initial commit - Windmill pipeline"

# Connect to GitHub
git remote add origin https://github.com/YOUR_USERNAME/windmill-postgres-project.git

# Push
git push -u origin main
```

### C. Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 6 secrets:

| Secret Name | Value | Where to get it |
|---|---|---|
| `WINDMILL_TOKEN` | `wm_xxx...` | Windmill UI → Settings → Tokens → New Token |
| `WINDMILL_WORKSPACE` | `default` | Check in Windmill UI URL |
| `WINDMILL_BASE_URL` | `http://YOUR_IP:8000` | Your server IP (not localhost) |
| `EMAIL_USER` | `your@gmail.com` | Your Gmail |
| `EMAIL_PASS` | `abcd efgh ijkl mnop` | Gmail App Password |
| `NOTIFY_EMAIL` | `destination@gmail.com` | Where to send reports |

**How to get Gmail App Password:**
1. Google Account → Security
2. Turn on **2-Step Verification**
3. Search "App passwords"
4. Create new → Select "Mail" → Copy the 16-char password

### D. Test Auto-Deploy

```bash
# Make a small change
echo "# Test" >> README.md

# Commit and push
git add .
git commit -m "Test auto-deploy"
git push origin main
```

Go to GitHub → **Actions** tab → You'll see the pipeline running!

After it completes:
1. Check Windmill UI → **Runs** → New job appeared
2. Check your email → You got a notification

✅ **Full CI/CD working!**

---

## 🎯 What Happens on `git push`

```
1. GitHub Actions triggers
2. Installs wmill CLI
3. Uploads run_pipeline.py to Windmill
4. Triggers Windmill job via API
5. Windmill executes the pipeline
6. Email sent
7. Job visible in Windmill UI
```

---

## 🔧 Troubleshooting

### Database connection failed
```bash
# Check postgres is running
docker ps

# Check logs
docker logs wm_postgres
```

### Windmill script error
- Make sure you copied the **entire** `run_pipeline.py` file
- Check the resource name matches (`my_postgres`)

### GitHub Actions not triggering
- Check you pushed to `main` branch (not `master`)
- Verify secrets are added correctly (no extra spaces)

### Email not working
- That's fine — pipeline still runs
- Just skip the email parameters

---

## 📊 View Pipeline Logs in Windmill

Every run is saved forever in Windmill:

1. **Runs** tab → Click any job
2. See:
   - Duration
   - Logs for each step
   - Final result JSON
   - Input parameters used

---

## 🧹 Clean Up

To stop everything:

```bash
docker compose down
```

To delete all data:

```bash
docker compose down -v
```

---

## 🎓 What You Learned

✅ Docker multi-container setup
✅ PostgreSQL with auto-init scripts
✅ Modular Python services (4 separate files)
✅ Shared volume for data passing
✅ Windmill UI integration
✅ GitHub Actions CI/CD
✅ Email notifications via SMTP

---

## 📚 Next Steps

1. **Modify filters** — Edit `services/process_data/process_data.py`
2. **Add more steps** — Create new service folder
3. **Create Windmill Flow** — Visual drag-and-drop in UI
4. **Schedule jobs** — Set up cron in Windmill
5. **Add more tables** — Extend `db/init.sql`

---

## 💡 Quick Commands Reference

```bash
# Start services
docker compose up -d postgres windmill

# Run pipeline (terminal)
./run_pipeline.sh

# Check table_a (source)
docker exec -it wm_postgres psql -U windmill -d windmill_db -c "SELECT * FROM table_a;"

# Check table_b (result)
docker exec -it wm_postgres psql -U windmill -d windmill_db -c "SELECT * FROM table_b;"

# Check logs
docker exec -it wm_postgres psql -U windmill -d windmill_db -c "SELECT * FROM pipeline_log;"

# View service logs
docker logs wm_postgres
docker logs windmill

# Stop everything
docker compose down

# Rebuild after code changes
docker compose build
```

---

## 🆘 Need Help?

If you get stuck:
1. Check logs: `docker logs wm_postgres` or `docker logs windmill`
2. Verify all files are present
3. Check docker is running: `docker ps`
4. Ensure port 5432 and 8000 are free

---

**You're all set! Start with STEP 1 above. 🚀**
