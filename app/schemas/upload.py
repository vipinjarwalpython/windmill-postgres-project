from pydantic import BaseModel

from app.models.file_upload import UploadStatus


class UploadResponse(BaseModel):
    upload_id: int
    original_filename: str
    stored_filename: str
    status: UploadStatus
    windmill_job_id: str | None = None
    message: str
