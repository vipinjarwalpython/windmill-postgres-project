from pathlib import Path
from typing import Any

import pandas as pd


REPORT_PATH = Path("/tmp/orders_report.csv")


def main(transform_result: dict[str, Any]) -> dict[str, Any]:
    """Save transformed records to a CSV report file."""
    if not transform_result.get("success"):
        raise ValueError("Transform step did not complete successfully.")

    records = transform_result.get("records", [])
    if not records:
        raise ValueError("No transformed records were found. CSV report was not created.")

    dataframe = pd.DataFrame(records)

    try:
        dataframe.to_csv(REPORT_PATH, index=False)
        return {
            "success": True,
            "file_path": str(REPORT_PATH),
            "row_count": int(len(dataframe)),
        }
    except Exception as error:
        raise RuntimeError(f"Failed to save CSV report: {error}") from error
