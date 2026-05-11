# services/load_data/load_data.py
# ══════════════════════════════════════════════════════════════
#  STEP 1 — LOAD DATA
#  ──────────────────
#  Connects to PostgreSQL and reads ALL rows from table_a.
#  Saves them to /shared/raw_data.json so the next
#  service (process_data) can pick them up.
#
#  Run:  python load_data.py
# ══════════════════════════════════════════════════════════════

import sys
import json
import os
from datetime import datetime

# allow importing from /app/config
sys.path.insert(0, "/app")
from config.db import get_connection, log_step


SHARED_DIR  = "/shared"
OUTPUT_FILE = os.path.join(SHARED_DIR, "raw_data.json")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_data():
    print(f"[{now()}] ▶  STEP 1 — Load Data started")

    conn = None
    try:
        # ── Connect ────────────────────────────────────────────
        conn = get_connection()
        print(f"[{now()}] ✔  Connected to database")

        # ── Read all rows from table_a ─────────────────────────
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, age, status, department, salary,
                       created_at::text
                FROM   table_a
                ORDER  BY id
                """
            )
            columns = [desc[0] for desc in cur.description]
            rows    = [dict(zip(columns, row)) for row in cur.fetchall()]

        print(f"[{now()}] ✔  Loaded {len(rows)} row(s) from table_a")

        # ── Save to shared volume as JSON ──────────────────────
        os.makedirs(SHARED_DIR, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(rows, f, indent=2, default=str)

        print(f"[{now()}] ✔  Saved raw data → {OUTPUT_FILE}")

        # ── Log success ────────────────────────────────────────
        log_step(conn, "load", "success",
                 f"Loaded {len(rows)} rows from table_a", len(rows))

        print(f"[{now()}] ✅  STEP 1 — Load Data complete\n")
        return len(rows)

    except Exception as e:
        print(f"[{now()}] ❌  STEP 1 ERROR: {e}")
        if conn:
            log_step(conn, "load", "error", str(e))
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    load_data()
