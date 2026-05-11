# services/notify/notify.py
# ══════════════════════════════════════════════════════════════
#  STEP 4 — NOTIFY
#  ─────────────────
#  Reads /shared/summary.json (output of Step 3).
#  Sends a plain-text email report via Gmail SMTP.
#
#  Required env vars (set in docker-compose.yml):
#      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL
#
#  Run:  python notify.py
# ══════════════════════════════════════════════════════════════

import sys
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

sys.path.insert(0, "/app")
from config.db import get_connection, log_step


SHARED_DIR   = "/shared"
SUMMARY_FILE = os.path.join(SHARED_DIR, "summary.json")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_email_body(summary: dict) -> str:
    rows = summary.get("stored_rows", [])

    rows_text = "\n".join(
        f"  • {r['name']:<12} age={r['age']:>2}  "
        f"dept={r.get('department','?'):<15} "
        f"salary={r.get('salary', 0):>10,.2f}"
        for r in rows
    ) or "  (no rows)"

    return f"""
Hi,

Your Windmill pipeline completed successfully.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PIPELINE SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Run time      : {summary.get('timestamp', '-')}
  Rows stored   : {summary.get('rows_stored', 0)}
  Errors        : {summary.get('errors', 0)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  FILTERED RECORDS (written to table_b):
{rows_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Filter rules applied:
  ✔  status  = 'active'
  ✔  age    >= 18

Regards,
Windmill Pipeline Bot
"""


def send_email(summary: dict):
    smtp_host  = os.getenv("SMTP_HOST",  "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))
    smtp_user  = os.getenv("SMTP_USER",  "")
    smtp_pass  = os.getenv("SMTP_PASSWORD", "")
    to_email   = os.getenv("NOTIFY_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        print(f"[{now()}] ⚠  SMTP_USER / SMTP_PASSWORD not set — skipping email")
        return False

    msg              = MIMEMultipart()
    msg["From"]      = smtp_user
    msg["To"]        = to_email
    msg["Subject"]   = (
        f"✅ Windmill Pipeline Done — "
        f"{summary.get('rows_stored', 0)} rows stored"
    )
    msg.attach(MIMEText(build_email_body(summary), "plain"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())

    print(f"[{now()}] ✔  Email sent to {to_email}")
    return True


def notify():
    print(f"[{now()}] ▶  STEP 4 — Notify started")

    conn = None
    try:
        # ── Read summary from Step 3 ──────────────────────────
        if not os.path.exists(SUMMARY_FILE):
            raise FileNotFoundError(
                f"{SUMMARY_FILE} not found. Did Step 3 (store_data) run?"
            )

        with open(SUMMARY_FILE, "r") as f:
            summary = json.load(f)

        print(f"[{now()}] ✔  Read summary: "
              f"{summary.get('rows_stored')} rows stored")

        # ── Send email ────────────────────────────────────────
        sent = send_email(summary)

        # ── Log to DB ─────────────────────────────────────────
        conn = get_connection()
        status_msg = "Email sent" if sent else "Email skipped (no SMTP config)"
        log_step(conn, "notify", "success", status_msg,
                 summary.get("rows_stored", 0))

        print(f"[{now()}] ✅  STEP 4 — Notify complete\n")

    except Exception as e:
        print(f"[{now()}] ❌  STEP 4 ERROR: {e}")
        if conn:
            log_step(conn, "notify", "error", str(e))
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    notify()
