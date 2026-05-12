import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


def _json_safe(value: Any) -> Any:
    """Convert database values into JSON-friendly values for Windmill."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Add it as a Windmill variable or environment variable."
        )
    return database_url


def main() -> dict:
    """Extract ecommerce orders from PostgreSQL and return them as JSON data."""
    query = """
        SELECT
            order_id,
            customer_name,
            customer_email,
            product_name,
            category,
            quantity,
            unit_price,
            order_status,
            order_date,
            shipping_city,
            payment_method
        FROM orders
        ORDER BY order_id;
    """

    try:
        with psycopg2.connect(_get_database_url()) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

        orders = [
            {key: _json_safe(value) for key, value in row.items()}
            for row in rows
        ]

        return {
            "success": True,
            "record_count": len(orders),
            "orders": orders,
        }

    except Exception as error:
        raise RuntimeError(f"Failed to extract orders from PostgreSQL: {error}") from error
