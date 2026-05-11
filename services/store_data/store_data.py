# services/store_data/store_data.py
# ══════════════════════════════════════════════════════════════
#  STEP 3 — STORE DATA
#  ─────────────────────
#  Reads /shared/processed_data.json (output of Step 2).
#  Inserts every filtered row into table_b in PostgreSQL.
#  Saves a summary to /shared/summary.json for Step 4 (notify).
#
#  Run:  python store_data.py
# ══════════════════════════════════════════════════════════════

import sys
import json
import os
from datetime import datetime

sys.path.insert(0, "/app")
from config.db import get_connection, log_step


SHARED_DIR    = "/shared"
INPUT_FILE    = os.path.join(SHARED_DIR, "processed_data.json")
SUMMARY_FILE  = os.path.join(SHARED_DIR, "summary.json")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def store_data():
    print(f"[{now()}] ▶  STEP 3 — Store Data started")

    conn = None
    try:
        # ── Read processed data from Step 2 ───────────────────
        if not os.path.exists(INPUT_FILE):
            raise FileNotFoundError(
                f"{INPUT_FILE} not found. Did Step 2 (process_data) run?"
            )

        with open(INPUT_FILE, "r") as f:
            rows = json.load(f)

        print(f"[{now()}] ✔  Read {len(rows)} processed row(s) from {INPUT_FILE}")

        # ── Connect and insert into table_b ───────────────────
        conn = get_connection()
        inserted = 0
        errors   = 0

        with conn.cursor() as cur:
            for row in rows:
                try:
                    cur.execute(
                        """
                        INSERT INTO table_b (name, age, status, department, salary)
                        VALUES (%(name)s, %(age)s, %(status)s,
                                %(department)s, %(salary)s)
                        """,
                        row,
                    )
                    inserted += 1
                    print(f"   ✔  Stored: {row['name']} "
                          f"| age={row['age']} "
                          f"| dept={row['department']} "
                          f"| salary={row['salary']}")
                except Exception as row_err:
                    errors += 1
                    print(f"   ✗  Failed row {row.get('name')}: {row_err}")

        conn.commit()
        print(f"\n[{now()}] ✔  DB commit done. "
              f"inserted={inserted}, errors={errors}")

        # ── Write summary for the notify service ──────────────
        summary = {
            "timestamp":    now(),
            "rows_stored":  inserted,
            "errors":       errors,
            "stored_rows":  rows,
        }
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"[{now()}] ✔  Summary saved → {SUMMARY_FILE}")

        # ── Log to DB ──────────────────────────────────────────
        log_step(conn, "store", "success",
                 f"Inserted {inserted} rows into table_b", inserted)

        print(f"[{now()}] ✅  STEP 3 — Store Data complete\n")
        return inserted

    except Exception as e:
        print(f"[{now()}] ❌  STEP 3 ERROR: {e}")
        if conn:
            log_step(conn, "store", "error", str(e))
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    store_data()
