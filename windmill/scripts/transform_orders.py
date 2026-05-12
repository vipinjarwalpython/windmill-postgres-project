from typing import Any

import pandas as pd


GST_RATE = 0.18


def main(extract_result: dict[str, Any]) -> dict[str, Any]:
    """Transform order data with pandas and build a useful summary."""
    if not extract_result.get("success"):
        raise ValueError("Extract step did not complete successfully.")

    orders = extract_result.get("orders", [])
    if not orders:
        return {
            "success": True,
            "records": [],
            "summary": {
                "total_orders": 0,
                "total_quantity": 0,
                "total_order_amount": 0.0,
                "total_gst_amount": 0.0,
                "total_final_amount": 0.0,
                "top_category": "N/A",
            },
        }

    dataframe = pd.DataFrame(orders)

    required_columns = {"quantity", "unit_price", "category"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns for transformation: {missing}")

    dataframe["quantity"] = pd.to_numeric(dataframe["quantity"])
    dataframe["unit_price"] = pd.to_numeric(dataframe["unit_price"])

    # Business rules: calculate base amount, GST, and customer final amount.
    dataframe["order_amount"] = (dataframe["quantity"] * dataframe["unit_price"]).round(2)
    dataframe["gst_amount"] = (dataframe["order_amount"] * GST_RATE).round(2)
    dataframe["final_amount"] = (
        dataframe["order_amount"] + dataframe["gst_amount"]
    ).round(2)

    top_category = (
        dataframe.groupby("category")["final_amount"]
        .sum()
        .sort_values(ascending=False)
        .index[0]
    )

    summary = {
        "total_orders": int(len(dataframe)),
        "total_quantity": int(dataframe["quantity"].sum()),
        "total_order_amount": float(dataframe["order_amount"].sum().round(2)),
        "total_gst_amount": float(dataframe["gst_amount"].sum().round(2)),
        "total_final_amount": float(dataframe["final_amount"].sum().round(2)),
        "top_category": str(top_category),
    }

    return {
        "success": True,
        "records": dataframe.to_dict(orient="records"),
        "summary": summary,
    }
