"""Send notification emails directly from FastAPI (not via Windmill).

Why duplicate Windmill's email step?  Because Windmill's failures stay buried
in the worker's job log — admins have no way to see them in the console. By
also sending a "new upload" notice from FastAPI, we can:

* prove that SMTP works end-to-end without waiting for the flow
* audit-log every per-department attempt
* surface failures on the Pipeline / Activity pages with the real reason

If you don't want this, set ``EMAIL_NOTIFY_ON_UPLOAD=false`` in ``.env`` and
the upload service will skip the call.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from app.core.config import Settings
from app.models.file_upload import FileUpload
from app.services.smtp_service import SmtpService

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._smtp = SmtpService(settings)

    def _send_sync(self, *, dept: str, recipient: str, upload: FileUpload, username: str) -> None:
        cfg = self.settings.smtp_config
        msg = EmailMessage()
        msg["Subject"] = f"[Loan Pipeline] New upload received — {upload.original_filename}"
        msg["From"] = cfg["from_addr"] or cfg["username"]
        msg["To"] = recipient
        msg["X-Loan-Pipeline-Upload-Id"] = str(upload.id)
        msg["X-Loan-Pipeline-Department"] = dept
        msg.set_content(
            "Hello,\n\n"
            f"A new loan file has just been uploaded and the ingestion pipeline\n"
            f"has been triggered. Your {dept.upper()} rows will arrive shortly.\n\n"
            f"  • File:         {upload.original_filename}\n"
            f"  • Upload ID:    #{upload.id}\n"
            f"  • Uploaded by:  {username}\n"
            f"  • Triggered at: {datetime.now(timezone.utc).isoformat()}\n"
            f"  • Windmill job: {upload.windmill_job_id or '—'}\n\n"
            "You'll see the ingested rows on your dashboard once the worker finishes.\n\n"
            "— Loan Pipeline Console (automated message)\n"
        )

        server = self._smtp._open_connection()
        try:
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass

    async def notify_departments(
        self,
        *,
        upload: FileUpload,
        department_emails: dict[str, str],
        username: str,
    ) -> list[dict]:
        """Send a notification to each department. Returns a list of result dicts:
        ``{"dept": str, "email": str | None, "ok": bool, "error": str | None}``.

        Best-effort — never raises. Even if SMTP is unconfigured, returns
        per-dept entries so the caller can audit-log them.
        """

        results: list[dict] = []

        if not self._smtp.is_configured():
            for dept, email in department_emails.items():
                results.append(
                    {
                        "dept": dept,
                        "email": email or None,
                        "ok": False,
                        "error": "SMTP is not configured",
                    }
                )
            return results

        for dept, email in department_emails.items():
            if not email:
                results.append(
                    {"dept": dept, "email": None, "ok": False, "error": "No email configured for department"}
                )
                continue
            try:
                await asyncio.to_thread(
                    self._send_sync, dept=dept, recipient=email, upload=upload, username=username
                )
                results.append({"dept": dept, "email": email, "ok": True, "error": None})
            except smtplib.SMTPAuthenticationError as exc:
                logger.exception("email_auth_failed", extra={"department": dept})
                err = exc.smtp_error.decode("utf-8", "ignore") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
                results.append({"dept": dept, "email": email, "ok": False, "error": f"auth failed: {err}"})
            except smtplib.SMTPRecipientsRefused as exc:
                results.append({"dept": dept, "email": email, "ok": False, "error": f"recipient refused: {exc.recipients}"})
            except smtplib.SMTPSenderRefused as exc:
                err = exc.smtp_error.decode("utf-8", "ignore") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
                results.append({"dept": dept, "email": email, "ok": False, "error": f"sender refused: {err}"})
            except smtplib.SMTPException as exc:
                logger.exception("email_smtp_error", extra={"department": dept})
                results.append({"dept": dept, "email": email, "ok": False, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 — never let email failure crash the upload
                logger.exception("email_unexpected_error", extra={"department": dept})
                results.append({"dept": dept, "email": email, "ok": False, "error": str(exc)})

        return results
