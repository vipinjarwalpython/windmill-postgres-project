import logging
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.department_data import DEPARTMENT_MODELS
from app.schemas.ingest import IngestRequest, IngestResponse, IngestRow
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# Two rows are the same record when their source row id and content all match.
# Amounts are quantized to cents so they compare equal to the stored Numeric(12, 2) value.
_CENTS = Decimal("0.01")

# Postgres parses a tuple-IN `WHERE (a,b,c,d) IN ((...),(...),...)` clause into
# a deep AND/OR expression tree. With ~30k tuples it blows the 2MB stack-depth
# limit (asyncpg raises StatementTooComplexError). We batch the lookup so each
# query stays well below that — 1000 tuples × 4 cols = 4000 parameters, fine.
_DEDUP_BATCH = 1000

# How many rows to send to Postgres in a single bulk INSERT statement.
# Keeps the parameter count bounded for very large ingest payloads.
_INSERT_BATCH = 1000


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


def _dedup_key(row: IngestRow) -> tuple:
    """Identity of a department record — rows with a matching key are duplicates."""
    return (row.source_row_id, row.employee_name, row.amount.quantize(_CENTS), row.record_date)


async def _existing_keys(session: AsyncSession, model, keys: list[tuple]) -> set[tuple]:
    """Return the subset of ``keys`` that already exist in ``model``, fetched in
    safe-sized batches so the IN-tuple expression never overflows Postgres'
    statement stack."""
    seen: set[tuple] = set()
    if not keys:
        return seen
    for start in range(0, len(keys), _DEDUP_BATCH):
        chunk = keys[start : start + _DEDUP_BATCH]
        result = await session.execute(
            select(
                model.source_row_id,
                model.employee_name,
                model.amount,
                model.record_date,
            ).where(
                tuple_(
                    model.source_row_id,
                    model.employee_name,
                    model.amount,
                    model.record_date,
                ).in_(chunk)
            )
        )
        for source_row_id, employee_name, amount, record_date in result.all():
            seen.add(
                (source_row_id, employee_name, amount.quantize(_CENTS), record_date)
            )
    return seen


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

    rows_by_department: dict[str, list[IngestRow]] = defaultdict(list)
    for row in payload.rows:
        rows_by_department[row.department].append(row)

    inserted = {dept: 0 for dept in DEPARTMENT_MODELS}
    skipped = {dept: 0 for dept in DEPARTMENT_MODELS}

    for department, rows in rows_by_department.items():
        model = DEPARTMENT_MODELS[department]
        keys = [_dedup_key(row) for row in rows]

        # Pull existing keys in batches so re-uploads and workflow retries
        # don't insert the same record twice.
        seen = await _existing_keys(session, model, keys)

        # Build the to-insert list with within-payload dedup too.
        to_insert: list[dict] = []
        for row, key in zip(rows, keys):
            if key in seen:
                skipped[department] += 1
                continue
            seen.add(key)
            to_insert.append(
                {
                    "source_row_id": row.source_row_id,
                    "employee_name": row.employee_name,
                    "amount": row.amount,
                    "record_date": row.record_date,
                    "source_upload_id": payload.upload_id,
                }
            )

        # Bulk insert in batches — far faster than session.add() per row, and
        # keeps the parameter count per statement bounded.
        for start in range(0, len(to_insert), _INSERT_BATCH):
            batch = to_insert[start : start + _INSERT_BATCH]
            await session.execute(insert(model), batch)
        inserted[department] = len(to_insert)

    total_inserted = sum(inserted.values())
    total_skipped = sum(skipped.values())

    # Audit-log the callback so the Pipeline page can show "ingest happened"
    # independent of whether any rows were actually inserted (all duplicates
    # would otherwise look like nothing happened).
    audit = AuditService(session)
    await audit.record(
        action="ingest.received",
        resource_type="file_upload",
        actor_id=None,
        resource_id=str(payload.upload_id),
        detail=(
            f"received={len(payload.rows)} inserted={total_inserted} "
            f"skipped={total_skipped} "
            f"(fin={inserted['finance']}/{skipped['finance']}, "
            f"hr={inserted['hr']}/{skipped['hr']}, "
            f"sales={inserted['sales']}/{skipped['sales']})"
        ),
    )

    await session.commit()
    if total_skipped:
        logger.info(
            "ingest_duplicates_skipped",
            extra={
                "upload_id": payload.upload_id,
                "skipped_finance": skipped["finance"],
                "skipped_hr": skipped["hr"],
                "skipped_sales": skipped["sales"],
                "total_skipped": total_skipped,
            },
        )

    logger.info(
        "ingest_completed",
        extra={
            "upload_id": payload.upload_id,
            "inserted_finance": inserted["finance"],
            "inserted_hr": inserted["hr"],
            "inserted_sales": inserted["sales"],
            "skipped_finance": skipped["finance"],
            "skipped_hr": skipped["hr"],
            "skipped_sales": skipped["sales"],
            "total_skipped": total_skipped,
            "total": len(payload.rows),
        },
    )
    return IngestResponse(
        upload_id=payload.upload_id,
        inserted=inserted,
        skipped=skipped,
        total_skipped=total_skipped,
        total=len(payload.rows),
    )
