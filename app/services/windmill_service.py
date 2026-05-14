import logging
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings
from app.models.file_upload import FileUpload

logger = logging.getLogger(__name__)


class WindmillService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def trigger_upload_workflow(
        self,
        upload: FileUpload,
        username: str,
        department_emails: dict[str, str],
    ) -> str:
        """Trigger a Windmill flow and return a job identifier."""

        if self.settings.windmill_mock:
            job_id = f"mock-{uuid4()}"
            logger.info("windmill_mock_job_created", extra={"request_id": job_id})
            return job_id

        if not self.settings.windmill_token or self.settings.windmill_token.startswith("replace-"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Windmill token is not configured. Create a token in Windmill and set WINDMILL_TOKEN.",
            )

        api_url = (
            f"{self.settings.windmill_base_url.rstrip('/')}/api/w/"
            f"{self.settings.windmill_workspace}/jobs/run/f/"
            f"{self.settings.windmill_workflow_path}"
        )
        payload = {
            "upload_id": upload.id,
            "file_path": upload.storage_path,
            "original_filename": upload.original_filename,
            "user": username,
            "ingest_url": self.settings.ingest_callback_url,
            "ingest_token": self.settings.ingest_token,
            "department_emails": department_emails,
            "smtp_config": self.settings.smtp_config,
        }
        headers = {"Authorization": f"Bearer {self.settings.windmill_token}"}

        try:
            async with httpx.AsyncClient(timeout=self.settings.windmill_timeout_seconds) as client:
                response = await client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.exception("windmill_http_error")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Windmill rejected workflow trigger: {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("windmill_connection_error")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not connect to Windmill",
            ) from exc

        try:
            body = response.json()
        except ValueError:
            return response.text.strip().strip('"')

        return str(body.get("uuid") or body.get("job_id") or body.get("id") or body)
