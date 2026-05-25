from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
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
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a loan file (workflow trigger + notifications run in the background)",
)
async def upload_loan_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    upload = await UploadService(session, settings).store_upload(file, current_user)

    # Workflow trigger + dept emails run after the response is sent.
    background_tasks.add_task(
        UploadService.process_in_background,
        upload_id=upload.id,
        actor_id=current_user.id,
        actor_username=current_user.username,
        settings=settings,
    )

    return UploadResponse(
        upload_id=upload.id,
        original_filename=upload.original_filename,
        stored_filename=upload.stored_filename,
        status=upload.status,
        windmill_job_id=upload.windmill_job_id,
        message="File stored. Workflow trigger and notifications are running in the background.",
    )
