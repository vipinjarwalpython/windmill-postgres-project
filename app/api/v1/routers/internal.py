import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.department_data import DEPARTMENT_MODELS
from app.schemas.ingest import IngestRequest, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_ingest_token(
    x_ingest_token: str | None = Header(default=None, alias="X-Ingest-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_ingest_token or x_ingest_token != settings.ingest_token:
        logger.warning("ingest_token_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ingest token",
        )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Internal: insert department-split rows. Called by Windmill workflow.",
    dependencies=[Depends(_verify_ingest_token)],
)
async def ingest(
    payload: IngestRequest,
    session: AsyncSession = Depends(get_db_session),
):
    logger.info(
        "ingest_started",
        extra={"upload_id": payload.upload_id, "row_count": len(payload.rows)},
    )

    inserted = {dept: 0 for dept in DEPARTMENT_MODELS}
    for row in payload.rows:
        model = DEPARTMENT_MODELS[row.department]
        session.add(
            model(
                source_row_id=row.source_row_id,
                employee_name=row.employee_name,
                amount=row.amount,
                record_date=row.record_date,
                source_upload_id=payload.upload_id,
            )
        )
        inserted[row.department] += 1

    await session.commit()
    logger.info(
        "ingest_completed",
        extra={
            "upload_id": payload.upload_id,
            "inserted_finance": inserted["finance"],
            "inserted_hr": inserted["hr"],
            "inserted_sales": inserted["sales"],
            "total": len(payload.rows),
        },
    )
    return IngestResponse(upload_id=payload.upload_id, inserted=inserted, total=len(payload.rows))
