# windmill/scripts/run_pipeline.py
# ══════════════════════════════════════════════════════════════
#  Windmill Orchestrator Script
#  ─────────────────────────────
#  This is the single script you create in Windmill UI.
#  It calls each step's logic in order using the same
#  Python functions (no Docker needed inside Windmill).
#
#  Database credentials: passed as individual string parameters
#  (db_host, db_port, db_user, db_password, db_name)
#
#  Dependencies:
#    psycopg2-binary
# ══════════════════════════════════════════════════════════════

import json
import os
import smtplib
import psycopg2
import psycopg2.extras
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ── Helpers ───────────────────────────────────────────────────

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn(db_host: str, db_port: int, db_user: str, db_password: str, db_name: str):
    return psycopg2.connect(
        host=db_host, port=db_port,
        user=db_user, password=db_password,
        dbname=db_name,
    )


def log_step(conn, step, status, message, rows=0):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_log (step,status,message,rows_count) "
            "VALUES (%s,%s,%s,%s)",
            (step, status, message, rows),
        )
    conn.commit()


# ── STEP 1: Load ──────────────────────────────────────────────

def step_load(db_host: str, db_port: int, db_user: str, db_password: str, db_name: str) -> list:
    print(f"[{now()}] ▶ STEP 1 — Load Data")
    conn = get_conn(db_host, db_port, db_user, db_password, db_name)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, age, status, department, salary "
            "FROM table_a ORDER BY id"
        )
        rows = [dict(r) for r in cur.fetchall()]
    log_step(conn, "load", "success", f"Loaded {len(rows)} rows", len(rows))
    conn.close()
    print(f"[{now()}] ✅ Loaded {len(rows)} rows")
    return rows


# ── STEP 2: Process ───────────────────────────────────────────

def step_process(raw_rows: list) -> list:
    print(f"[{now()}] ▶ STEP 2 — Process Data")
    filtered = [
        r for r in raw_rows
        if r["status"] == "active" and r["age"] >= 18
    ]
    print(f"[{now()}] ✅ Filtered: {len(raw_rows)} → {len(filtered)} rows")
    return filtered


# ── STEP 3: Store ─────────────────────────────────────────────

def step_store(db_host: str, db_port: int, db_user: str, db_password: str, db_name: str, rows: list) -> int:
    print(f"[{now()}] ▶ STEP 3 — Store Data")
    print(f"[{now()}] ▶ STEP 3 — Store Data")
    conn = get_conn(db_host, db_port, db_user, db_password, db_name)
    inserted = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO table_b (name, age, status, department, salary) "
                "VALUES (%(name)s, %(age)s, %(status)s, %(department)s, %(salary)s)",
                r,
            )
            inserted += 1
    conn.commit()
    log_step(conn, "store", "success", f"Inserted {inserted} rows", inserted)
    conn.close()
    print(f"[{now()}] ✅ Stored {inserted} rows into table_b")
    return inserted


# ── STEP 4: Notify ────────────────────────────────────────────

def step_notify(db_host: str, db_port: int, db_user: str, db_password: str, db_name: str, rows: list, inserted: int,
                smtp_user: str, smtp_pass: str, to_email: str):
    print(f"[{now()}] ▶ STEP 4 — Notify")
    if not smtp_user or not smtp_pass:
        print(f"[{now()}] ⚠ SMTP not configured — skipping email")
        return

    body = f"""
Pipeline completed!

Rows stored : {inserted}
Timestamp   : {now()}

Records written to table_b:
""" + "\n".join(f"  • {r['name']} age={r['age']} dept={r['department']}" for r in rows)

    msg           = MIMEMultipart()
    msg["From"]   = smtp_user
    msg["To"]     = to_email
    msg["Subject"] = f"✅ Windmill Pipeline Done — {inserted} rows stored"
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.sendmail(smtp_user, to_email, msg.as_string())

    conn = get_conn(db_host, db_port, db_user, db_password, db_name)
    log_step(conn, "notify", "success", f"Email sent to {to_email}", inserted)
    conn.close()
    print(f"[{now()}] ✅ Email sent to {to_email}")


# ── Windmill entry point ──────────────────────────────────────

def main(
    db_host: str = "postgres",
    db_port: int = 5432,
    db_user: str = "windmill",
    db_password: str = "windmill123",
    db_name: str = "windmill_db",
    smtp_user: str  = "",              # Gmail address
    smtp_pass: str  = "",              # Gmail App Password
    notify_email: str = "",            # destination email
):
    raw      = step_load(db_host, db_port, db_user, db_password, db_name)
    filtered = step_process(raw)
    inserted = step_store(db_host, db_port, db_user, db_password, db_name, filtered)
    step_notify(db_host, db_port, db_user, db_password, db_name, filtered, inserted, smtp_user, smtp_pass,
                notify_email or smtp_user)

    return {
        "status":        "success",
        "timestamp":     now(),
        "rows_loaded":   len(raw),
        "rows_filtered": len(filtered),
        "rows_stored":   inserted,
    }
