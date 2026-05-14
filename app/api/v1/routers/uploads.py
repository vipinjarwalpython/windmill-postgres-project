from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rbac import require_roles
from app.db.session import get_db_session
from app.models.user import Role, User
from app.schemas.upload import UploadResponse
from app.services.upload_service import UploadService


router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "/loan",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a loan file and trigger a Windmill workflow",
)
async def upload_loan_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    upload = await UploadService(session, settings).upload_and_trigger(file, current_user)
    return UploadResponse(
        upload_id=upload.id,
        original_filename=upload.original_filename,
        stored_filename=upload.stored_filename,
        status=upload.status,
        windmill_job_id=upload.windmill_job_id,
        message="File stored and workflow triggered",
    )
