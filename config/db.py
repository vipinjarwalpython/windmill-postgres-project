# config/db.py
# ─────────────────────────────────────────────
# Shared database connection helper.
# All services import from here — one place to
# change DB settings if needed.
# ─────────────────────────────────────────────

import os
import psycopg2
import psycopg2.extras


def get_connection():
    """
    Returns a live psycopg2 connection using env variables.
    Set in docker-compose.yml or .env file.
    """
    return psycopg2.connect(
        host     = os.getenv("DB_HOST",     "postgres"),
        port     = int(os.getenv("DB_PORT", "5432")),
        user     = os.getenv("DB_USER",     "windmill"),
        password = os.getenv("DB_PASSWORD", "windmill123"),
        dbname   = os.getenv("DB_NAME",     "windmill_db"),
    )


def log_step(conn, step: str, status: str, message: str, rows: int = 0):
    """
    Write a row to pipeline_log table so every run is traceable.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_log (step, status, message, rows_count)
            VALUES (%s, %s, %s, %s)
            """,
            (step, status, message, rows),
        )
    conn.commit()
