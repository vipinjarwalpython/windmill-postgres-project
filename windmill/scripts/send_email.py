import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is missing. Add it as a Windmill variable or secret.")
    return value


def _build_email_body(summary: dict[str, Any], row_count: int) -> str:
    return f"""Hello,

The orders ETL pipeline completed successfully.

Summary:
- Orders processed: {summary.get("total_orders", 0)}
- CSV rows generated: {row_count}
- Total quantity sold: {summary.get("total_quantity", 0)}
- Total order amount: {summary.get("total_order_amount", 0.0)}
- Total GST amount: {summary.get("total_gst_amount", 0.0)}
- Total final amount: {summary.get("total_final_amount", 0.0)}
- Top category by revenue: {summary.get("top_category", "N/A")}

The CSV report is attached.

Regards,
Windmill ETL Automation
"""


def main(transform_result: dict[str, Any], save_csv_result: dict[str, Any]) -> dict[str, Any]:
    """Email the generated CSV report as an attachment."""
    if not transform_result.get("success"):
        raise ValueError("Transform step did not complete successfully.")

    if not save_csv_result.get("success"):
        raise ValueError("CSV save step did not complete successfully.")

    smtp_host = _get_required_env("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = _get_required_env("SMTP_USERNAME")
    smtp_password = _get_required_env("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", smtp_username)
    email_to = _get_required_env("EMAIL_TO")

    csv_path = Path(save_csv_result["file_path"])
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV report was not found at {csv_path}")

    message = EmailMessage()
    message["Subject"] = "Orders ETL Pipeline Report"
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(
        _build_email_body(
            transform_result.get("summary", {}),
            int(save_csv_result.get("row_count", 0)),
        )
    )

    csv_bytes = csv_path.read_bytes()
    message.add_attachment(
        csv_bytes,
        maintype="text",
        subtype="csv",
        filename=csv_path.name,
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)

        return {
            "success": True,
            "email_to": email_to,
            "attachment": str(csv_path),
        }

    except Exception as error:
        raise RuntimeError(f"Failed to send report email: {error}") from error
