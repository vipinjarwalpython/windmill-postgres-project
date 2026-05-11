# services/process_data/process_data.py
# ══════════════════════════════════════════════════════════════
#  STEP 2 — PROCESS / FILTER DATA
#  ────────────────────────────────
#  Reads /shared/raw_data.json (output of Step 1).
#  Applies filter rules:
#      ✔  status  == 'active'
#      ✔  age     >= 18
#  Saves filtered rows to /shared/processed_data.json
#  for Step 3 (store_data) to consume.
#
#  Run:  python process_data.py
# ══════════════════════════════════════════════════════════════

import sys
import json
import os
from datetime import datetime

sys.path.insert(0, "/app")
from config.db import get_connection, log_step


SHARED_DIR     = "/shared"
INPUT_FILE     = os.path.join(SHARED_DIR, "raw_data.json")
OUTPUT_FILE    = os.path.join(SHARED_DIR, "processed_data.json")

# ── Filter rules (easy to change / extend) ────────────────────
FILTER_STATUS  = "active"
FILTER_MIN_AGE = 18


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def apply_filters(rows: list) -> list:
    """
    Returns only rows that pass ALL filter conditions.
    Add more conditions here as your project grows.
    """
    filtered = []
    for row in rows:
        passes = (
            row.get("status") == FILTER_STATUS   # must be active
            and row.get("age", 0) >= FILTER_MIN_AGE  # must be adult
        )
        if passes:
            filtered.append(row)
        else:
            print(f"   ✗  Skipped: {row['name']} "
                  f"(age={row['age']}, status={row['status']})")
    return filtered


def process_data():
    print(f"[{now()}] ▶  STEP 2 — Process Data started")

    conn = None
    try:
        # ── Read raw data written by Step 1 ───────────────────
        if not os.path.exists(INPUT_FILE):
            raise FileNotFoundError(
                f"{INPUT_FILE} not found. Did Step 1 (load_data) run?"
            )

        with open(INPUT_FILE, "r") as f:
            raw_rows = json.load(f)

        print(f"[{now()}] ✔  Read {len(raw_rows)} raw row(s) from {INPUT_FILE}")
        print(f"[{now()}]    Applying filters: "
              f"status='{FILTER_STATUS}', age>={FILTER_MIN_AGE}")

        # ── Apply filter logic ─────────────────────────────────
        filtered = apply_filters(raw_rows)

        print(f"\n[{now()}] ✔  Filter result: "
              f"{len(filtered)} kept / {len(raw_rows) - len(filtered)} removed")

        # ── Save filtered data ─────────────────────────────────
        with open(OUTPUT_FILE, "w") as f:
            json.dump(filtered, f, indent=2, default=str)

        print(f"[{now()}] ✔  Saved processed data → {OUTPUT_FILE}")

        # ── Log to DB ──────────────────────────────────────────
        conn = get_connection()
        log_step(conn, "process", "success",
                 f"Filtered {len(raw_rows)} → {len(filtered)} rows",
                 len(filtered))

        print(f"[{now()}] ✅  STEP 2 — Process Data complete\n")
        return len(filtered)

    except Exception as e:
        print(f"[{now()}] ❌  STEP 2 ERROR: {e}")
        if conn:
            log_step(conn, "process", "error", str(e))
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    process_data()
