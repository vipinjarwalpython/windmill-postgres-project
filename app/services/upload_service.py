import logging
import re
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.models.department_settings import DepartmentSetting
from app.models.file_upload import FileUpload, UploadStatus
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.services.windmill_service import WindmillService


logger = logging.getLogger(__name__)
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class UploadService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.audit = AuditService(session)
        self.windmill = WindmillService(settings)
        self.email = EmailService(settings)

    # ------------------------------------------------------------------
    # Phase 1 — fast: save the file and create the DB row, then return.
    # ------------------------------------------------------------------
    async def store_upload(self, file: UploadFile, current_user: User) -> FileUpload:
        original_name = Path(file.filename or "upload.bin").name
        extension = Path(original_name).suffix.lower()
        allowed_extensions = self.settings.allowed_upload_extension_list
        if extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
            )

        safe_base = SAFE_FILENAME_PATTERN.sub("_", Path(original_name).stem).strip("._") or "upload"
        stored_name = f"{uuid4()}-{safe_base}{extension}"
        storage_dir = self.settings.storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / stored_name

        size = await self._write_file_with_limit(file, storage_path)
        upload = FileUpload(
            original_filename=original_name,
            stored_filename=stored_name,
            storage_path=str(storage_path),
            content_type=file.content_type or "application/octet-stream",
            size_bytes=size,
            owner_id=current_user.id,
            status=UploadStatus.stored,
        )
        self.session.add(upload)
        await self.session.flush()
        await self.session.refresh(upload)

        await self.audit.record(
            action="file.stored",
            resource_type="file_upload",
            actor_id=current_user.id,
            resource_id=str(upload.id),
            detail=f"Stored {original_name} as {stored_name}",
        )
        await self.session.commit()
        await self.session.refresh(upload)
        return upload

    # ------------------------------------------------------------------
    # Phase 2 — slow: trigger Windmill and send notifications. Runs
    # in a background task on its OWN database session so the request
    # session is free to return to the user.
    # ------------------------------------------------------------------
    @staticmethod
    async def process_in_background(
        *,
        upload_id: int,
        actor_id: int,
        actor_username: str,
        settings: Settings,
    ) -> None:
        """Trigger Windmill + send dept notification emails for an already-stored upload.

        Always runs to completion — failures are recorded on the upload row
        and in the audit log, never raised (this runs after the response was
        already sent).
        """
        async with AsyncSessionLocal() as session:
            try:
                upload = await session.get(FileUpload, upload_id)
                if upload is None:
                    logger.warning("background_upload_not_found", extra={"upload_id": upload_id})
                    return

                service = UploadService(session, settings)
                audit = AuditService(session)
                windmill = WindmillService(settings)
                email = EmailService(settings)

                # Read dept emails before triggering — they're forwarded to Windmill.
                dept_emails = await service._get_department_emails()

                try:
                    job_id = await windmill.trigger_upload_workflow(
                        upload, actor_username, dept_emails
                    )
                    upload.windmill_job_id = job_id
                    upload.status = UploadStatus.workflow_triggered
                    await audit.record(
                        action="workflow.triggered",
                        resource_type="windmill_job",
                        actor_id=actor_id,
                        resource_id=job_id,
                        detail=f"Triggered workflow for upload {upload.id}",
                    )
                except Exception as exc:  # noqa: BLE001 — log + persist, never re-raise
                    logger.exception("background_windmill_trigger_failed", extra={"upload_id": upload_id})
                    upload.status = UploadStatus.workflow_failed
                    await audit.record(
                        action="workflow.failed",
                        resource_type="file_upload",
                        actor_id=actor_id,
                        resource_id=str(upload.id),
                        detail=f"Trigger failed: {exc}",
                    )
                    await session.commit()
                    return

                await session.commit()

                # Best-effort department notifications. Each result is audit-logged
                # so the Pipeline page reflects what really happened.
                if settings.email_notify_on_upload:
                    results = await email.notify_departments(
                        upload=upload, department_emails=dept_emails, username=actor_username
                    )
                    for r in results:
                        action = "email.dispatched" if r["ok"] else "email.failed"
                        target = r.get("email") or "—"
                        detail = (
                            f"{r['dept']} → {target}"
                            if r["ok"]
                            else f"{r['dept']} → {target}: {r.get('error') or 'unknown error'}"
                        )
                        await audit.record(
                            action=action,
                            resource_type="file_upload",
                            actor_id=actor_id,
                            resource_id=str(upload.id),
                            detail=detail,
                        )
                    await session.commit()
            except Exception:
                logger.exception("background_upload_unhandled_error", extra={"upload_id": upload_id})
                try:
                    await session.rollback()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _get_department_emails(self) -> dict[str, str]:
        result = await self.session.execute(select(DepartmentSetting))
        return {setting.department: setting.email for setting in result.scalars().all()}

    async def _write_file_with_limit(self, file: UploadFile, destination: Path) -> int:
        total = 0
        async with aiofiles.open(destination, "wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > self.settings.max_upload_bytes:
                    await output.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Uploaded file is too large",
                    )
                await output.write(chunk)
        return total
