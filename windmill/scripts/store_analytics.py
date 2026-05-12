import os
from typing import Any

import psycopg2
from psycopg2.extras import execute_values


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Add it as a Windmill variable or environment variable."
        )
    return database_url


def main(transform_result: dict[str, Any]) -> dict[str, Any]:
    """Insert transformed orders into the analytics_orders table."""
    if not transform_result.get("success"):
        raise ValueError("Transform step did not complete successfully.")

    records = transform_result.get("records", [])
    if not records:
        return {
            "success": True,
            "inserted_count": 0,
            "message": "No records to insert.",
        }

    insert_sql = """
        INSERT INTO analytics_orders (
            order_id,
            customer_name,
            customer_email,
            product_name,
            category,
            quantity,
            unit_price,
            order_amount,
            gst_amount,
            final_amount,
            order_status,
            order_date,
            shipping_city,
            payment_method
        ) VALUES %s;
    """

    values = [
        (
            record["order_id"],
            record["customer_name"],
            record["customer_email"],
            record["product_name"],
            record["category"],
            record["quantity"],
            record["unit_price"],
            record["order_amount"],
            record["gst_amount"],
            record["final_amount"],
            record["order_status"],
            record["order_date"],
            record["shipping_city"],
            record["payment_method"],
        )
        for record in records
    ]

    try:
        with psycopg2.connect(_get_database_url()) as connection:
            with connection.cursor() as cursor:
                execute_values(cursor, insert_sql, values)
            connection.commit()

        return {
            "success": True,
            "inserted_count": len(values),
        }

    except Exception as error:
        raise RuntimeError(f"Failed to insert analytics records: {error}") from error
