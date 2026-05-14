import re
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.department_settings import DepartmentSetting
from app.models.file_upload import FileUpload, UploadStatus
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.windmill_service import WindmillService


SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class UploadService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.audit = AuditService(session)
        self.windmill = WindmillService(settings)

    async def upload_and_trigger(self, file: UploadFile, current_user: User) -> FileUpload:
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

        try:
            department_emails = await self._get_department_emails()
            job_id = await self.windmill.trigger_upload_workflow(
                upload, current_user.username, department_emails
            )
            upload.windmill_job_id = job_id
            upload.status = UploadStatus.workflow_triggered
            await self.audit.record(
                action="workflow.triggered",
                resource_type="windmill_job",
                actor_id=current_user.id,
                resource_id=job_id,
                detail=f"Triggered workflow for upload {upload.id}",
            )
        except Exception:
            upload.status = UploadStatus.workflow_failed
            await self.session.commit()
            raise

        await self.session.commit()
        await self.session.refresh(upload)
        return upload

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
