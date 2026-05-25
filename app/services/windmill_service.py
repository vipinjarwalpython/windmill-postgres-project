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

    async def get_job_status(self, job_id: str | None) -> dict | None:
        """Look up a Windmill job's status.

        Returns one of:
        * ``{"state": "success", ...}``  — job completed successfully
        * ``{"state": "failure", "error": "..."}`` — job finished with an error
        * ``{"state": "running", ...}``  — job is still queued or in flight
        * ``{"state": "unknown", "reason": "..."}`` — couldn't reach Windmill
                                                     (mock mode, network, 4xx, etc.)
        * ``None`` — nothing to query (no job_id, or it's a mock id)

        Safe to call in a loop: catches all errors so a page render never fails
        because Windmill is unreachable.
        """
        if not job_id or job_id.startswith("mock-"):
            return None
        if self.settings.windmill_mock:
            return None
        if not self.settings.windmill_token or self.settings.windmill_token.startswith("replace-"):
            return {"state": "unknown", "reason": "WINDMILL_TOKEN is not configured"}

        base = self.settings.windmill_base_url.rstrip("/")
        ws = self.settings.windmill_workspace
        headers = {"Authorization": f"Bearer {self.settings.windmill_token}"}
        # Windmill has separate routes for in-flight vs completed jobs.
        # Try completed first (fast for the common case), then queued.
        urls = (
            f"{base}/api/w/{ws}/jobs_u/completed/get/{job_id}",
            f"{base}/api/w/{ws}/jobs_u/get/{job_id}",
        )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                for url in urls:
                    try:
                        resp = await client.get(url, headers=headers)
                    except httpx.HTTPError as exc:
                        logger.debug("windmill_status_http_error", extra={"url": url, "err": str(exc)})
                        continue
                    if resp.status_code == 404:
                        continue
                    if resp.status_code >= 400:
                        return {
                            "state": "unknown",
                            "reason": f"Windmill returned HTTP {resp.status_code}",
                        }
                    try:
                        body = resp.json()
                    except ValueError:
                        return {"state": "unknown", "reason": "Non-JSON response"}
                    return self._parse_job_status(body, url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("windmill_status_unexpected_error", extra={"err": str(exc)})
            return {"state": "unknown", "reason": str(exc)}

        return {"state": "unknown", "reason": "Job not found in Windmill"}

    @staticmethod
    def _parse_job_status(body: dict, source_url: str) -> dict:
        # Completed jobs have ``success: true/false`` plus ``result``.
        # Queued/running jobs (jobs_u/get) have ``running`` flag.
        is_completed = "/completed/" in source_url
        if is_completed:
            success = bool(body.get("success"))
            return {
                "state": "success" if success else "failure",
                "job_id": body.get("id"),
                "completed_at": body.get("started_at") or body.get("created_at"),
                "duration_ms": body.get("duration_ms"),
                "error": (body.get("result") or {}).get("error") if not success else None,
                "raw": body,
            }
        running = bool(body.get("running"))
        return {
            "state": "running" if running else "queued",
            "job_id": body.get("id"),
            "started_at": body.get("started_at"),
            "raw": body,
        }
