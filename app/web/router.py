import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.audit_log import AuditLog
from app.models.department_data import DEPARTMENT_MODELS, FinanceData, HRData, SalesData
from app.models.file_upload import FileUpload, UploadStatus
from app.models.user import Role, User
from app.schemas.auth import UserLogin
from app.services.auth_service import AuthService
from app.services.smtp_service import SmtpService
from app.services.upload_service import UploadService
from app.services.windmill_service import WindmillService
from app.web.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_web_user,
    get_optional_web_user,
    require_web_roles,
)


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


def _role_label(role: Role) -> str:
    return {
        Role.admin: "Administrator",
        Role.finance: "Finance",
        Role.hr: "Human Resources",
        Role.sales: "Sales",
    }.get(role, role.value.title())


def _role_badge_class(role: Role) -> str:
    return {
        Role.admin: "badge-admin",
        Role.finance: "badge-finance",
        Role.hr: "badge-hr",
        Role.sales: "badge-sales",
    }.get(role, "badge-default")


def _common_context(request: Request, user: User, settings: Settings) -> dict:
    return {
        "request": request,
        "user": user,
        "role_label": _role_label(user.role),
        "role_badge_class": _role_badge_class(user.role),
        "app_name": settings.app_name,
        "now": datetime.now(timezone.utc),
    }


@router.get("/")
async def index(user: User | None = Depends(get_optional_web_user)):
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login")
async def login_page(
    request: Request,
    user: User | None = Depends(get_optional_web_user),
    settings: Settings = Depends(get_settings),
):
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "app_name": settings.app_name, "error": None},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    try:
        credentials = UserLogin(username=username, password=password)
    except ValidationError:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "error": "Please enter both a username and password.",
                "username": username,
            },
            status_code=400,
        )

    try:
        token = await AuthService(session).login(credentials)
    except HTTPException as exc:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "error": exc.detail,
                "username": username,
            },
            status_code=exc.status_code,
        )

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "local",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


PAGE_SIZE_CHOICES = (10, 25, 50, 100)


async def _upload_metrics(session: AsyncSession) -> dict:
    total = (await session.execute(select(func.count(FileUpload.id)))).scalar_one() or 0
    triggered = (
        await session.execute(
            select(func.count(FileUpload.id)).where(FileUpload.status == UploadStatus.workflow_triggered)
        )
    ).scalar_one() or 0
    failed = (
        await session.execute(
            select(func.count(FileUpload.id)).where(FileUpload.status == UploadStatus.workflow_failed)
        )
    ).scalar_one() or 0
    stored = (
        await session.execute(
            select(func.count(FileUpload.id)).where(FileUpload.status == UploadStatus.stored)
        )
    ).scalar_one() or 0
    total_bytes = (await session.execute(select(func.coalesce(func.sum(FileUpload.size_bytes), 0)))).scalar_one() or 0

    success_rate = round((triggered / total) * 100) if total else 0
    return {
        "total": total,
        "triggered": triggered,
        "failed": failed,
        "stored": stored,
        "total_bytes": int(total_bytes),
        "success_rate": success_rate,
    }


async def _department_counts(session: AsyncSession) -> dict:
    finance = (await session.execute(select(func.count(FinanceData.id)))).scalar_one() or 0
    hr = (await session.execute(select(func.count(HRData.id)))).scalar_one() or 0
    sales = (await session.execute(select(func.count(SalesData.id)))).scalar_one() or 0
    return {"finance": finance, "hr": hr, "sales": sales, "total": finance + hr + sales}


async def _department_amounts(session: AsyncSession) -> dict:
    finance = (await session.execute(select(func.coalesce(func.sum(FinanceData.amount), 0)))).scalar_one() or 0
    hr = (await session.execute(select(func.coalesce(func.sum(HRData.amount), 0)))).scalar_one() or 0
    sales = (await session.execute(select(func.coalesce(func.sum(SalesData.amount), 0)))).scalar_one() or 0
    return {
        "finance": float(finance),
        "hr": float(hr),
        "sales": float(sales),
        "total": float(finance) + float(hr) + float(sales),
    }


async def _uploads_per_day(session: AsyncSession, days: int = 7) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    result = await session.execute(
        select(
            func.date(FileUpload.created_at).label("d"),
            func.count(FileUpload.id).label("c"),
        )
        .where(FileUpload.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
        .group_by(func.date(FileUpload.created_at))
    )
    raw = {row.d: row.c for row in result.all()}
    series: list[dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        label = d.strftime("%a")
        series.append({"label": label, "date": d.isoformat(), "value": int(raw.get(d, 0))})
    return series


async def _ingest_per_day(session: AsyncSession, days: int = 7) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)

    series: list[dict] = []
    raw: dict = {}
    for model in (FinanceData, HRData, SalesData):
        result = await session.execute(
            select(
                func.date(model.created_at).label("d"),
                func.count(model.id).label("c"),
            )
            .where(model.created_at >= start_dt)
            .group_by(func.date(model.created_at))
        )
        for row in result.all():
            raw[row.d] = raw.get(row.d, 0) + row.c

    for i in range(days):
        d = start + timedelta(days=i)
        series.append({"label": d.strftime("%a"), "date": d.isoformat(), "value": int(raw.get(d, 0))})
    return series


async def _recent_uploads(session: AsyncSession, limit: int = 10) -> list[FileUpload]:
    result = await session.execute(
        select(FileUpload).order_by(FileUpload.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def _recent_activity(session: AsyncSession, limit: int = 8) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def _user_activity(session: AsyncSession, user_id: int, limit: int = 8) -> list[AuditLog]:
    """Activity log entries scoped to a single user (department-user view)."""
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.actor_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _dept_metrics(session: AsyncSession, model) -> dict:
    """Department-only KPIs: row count, total amount, avg amount, last ingest."""
    total = (await session.execute(select(func.count(model.id)))).scalar_one() or 0
    total_amount = (
        await session.execute(select(func.coalesce(func.sum(model.amount), 0)))
    ).scalar_one() or 0
    last_at = (await session.execute(select(func.max(model.created_at)))).scalar_one()
    avg_amount = (float(total_amount) / total) if total else 0.0
    return {
        "total": int(total),
        "total_amount": float(total_amount),
        "avg_amount": avg_amount,
        "last_at": last_at,
    }


async def _dept_ingest_per_day(session: AsyncSession, model, days: int = 7) -> list[dict]:
    """Daily ingest counts for ONE department only."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    result = await session.execute(
        select(
            func.date(model.created_at).label("d"),
            func.count(model.id).label("c"),
        )
        .where(model.created_at >= start_dt)
        .group_by(func.date(model.created_at))
    )
    raw = {row.d: row.c for row in result.all()}
    series: list[dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        series.append({"label": d.strftime("%a"), "date": d.isoformat(), "value": int(raw.get(d, 0))})
    return series


@router.get("/dashboard")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_web_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    page: int = Query(1),
    page_size: int = Query(25),
    q: str | None = Query(None),
):
    if page < 1:
        page = 1
    query_term = (q or "").strip()
    context = _common_context(request, user, settings)
    is_admin = user.role == Role.admin
    department = None if is_admin else user.role.value

    department_rows: list = []
    pagination = None
    if department and department in DEPARTMENT_MODELS:
        if page_size not in PAGE_SIZE_CHOICES:
            page_size = 25
        model = DEPARTMENT_MODELS[department]

        count_stmt = select(func.count(model.id))
        list_stmt = select(model).order_by(model.created_at.desc(), model.id.desc())
        if query_term:
            like = f"%{query_term}%"
            count_stmt = count_stmt.where(model.employee_name.ilike(like))
            list_stmt = list_stmt.where(model.employee_name.ilike(like))

        total = (await session.execute(count_stmt)).scalar_one()
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size

        result = await session.execute(list_stmt.offset(offset).limit(page_size))
        department_rows = list(result.scalars().all())

        first_index = offset + 1 if total else 0
        last_index = offset + len(department_rows)
        pagination = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "first_index": first_index,
            "last_index": last_index,
            "size_choices": PAGE_SIZE_CHOICES,
            "q": query_term,
        }

    if is_admin:
        # Admin sees pipeline-wide metrics across all departments.
        upload_metrics = await _upload_metrics(session)
        dept_counts = await _department_counts(session)
        dept_amounts = await _department_amounts(session)
        uploads_series = await _uploads_per_day(session, days=7)
        ingest_series = await _ingest_per_day(session, days=7)
        recent_uploads = await _recent_uploads(session, limit=6)

        context.update(
            {
                "can_upload": True,
                "is_admin": True,
                "department": None,
                "department_rows": [],
                "pagination": None,
                "metrics": upload_metrics,
                "dept_counts": dept_counts,
                "dept_amounts": dept_amounts,
                "uploads_series": uploads_series,
                "ingest_series": ingest_series,
                "recent_uploads": recent_uploads,
                "status_badge_class": _status_badge_class,
                "format_size": _format_size,
            }
        )
    else:
        # Department user sees ONLY their own department's data.
        model = DEPARTMENT_MODELS.get(department) if department else None
        dept_metrics = (
            await _dept_metrics(session, model) if model else {"total": 0, "total_amount": 0.0, "avg_amount": 0.0, "last_at": None}
        )
        dept_series = (
            await _dept_ingest_per_day(session, model, days=14) if model else []
        )

        context.update(
            {
                "can_upload": False,
                "is_admin": False,
                "department": department,
                "department_rows": department_rows,
                "pagination": pagination,
                "dept_metrics": dept_metrics,
                "dept_series": dept_series,
                "status_badge_class": _status_badge_class,
                "format_size": _format_size,
            }
        )

    return templates.TemplateResponse("dashboard.html", context)


def _status_badge_class(status_value: str) -> str:
    return {
        "stored": "badge-status-stored",
        "workflow_triggered": "badge-status-ok",
        "workflow_failed": "badge-status-fail",
    }.get(status_value, "badge-default")


def _format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


UPLOAD_STATUS_FILTERS = {
    "all": None,
    "stored": UploadStatus.stored,
    "workflow_triggered": UploadStatus.workflow_triggered,
    "workflow_failed": UploadStatus.workflow_failed,
}


async def _filtered_uploads(
    session: AsyncSession,
    *,
    query_term: str = "",
    status_filter: str = "all",
    page: int,
    page_size: int,
) -> tuple[list[FileUpload], dict]:
    if page_size not in PAGE_SIZE_CHOICES:
        page_size = 25
    if page < 1:
        page = 1

    count_stmt = select(func.count(FileUpload.id))
    list_stmt = select(FileUpload).order_by(FileUpload.created_at.desc())

    if query_term:
        like = f"%{query_term}%"
        cond = or_(
            FileUpload.original_filename.ilike(like),
            FileUpload.windmill_job_id.ilike(like),
        )
        count_stmt = count_stmt.where(cond)
        list_stmt = list_stmt.where(cond)

    status_enum = UPLOAD_STATUS_FILTERS.get(status_filter)
    if status_enum is not None:
        count_stmt = count_stmt.where(FileUpload.status == status_enum)
        list_stmt = list_stmt.where(FileUpload.status == status_enum)

    total = (await session.execute(count_stmt)).scalar_one() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size

    result = await session.execute(list_stmt.offset(offset).limit(page_size))
    uploads = list(result.scalars().all())

    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "first_index": offset + 1 if total else 0,
        "last_index": offset + len(uploads),
        "size_choices": PAGE_SIZE_CHOICES,
        "q": query_term,
        "status": status_filter,
    }
    return uploads, pagination


@router.get("/uploads")
async def uploads_page(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    page: int = Query(1),
    page_size: int = Query(25),
    q: str | None = Query(None),
    status: str = Query("all"),
):
    context = _common_context(request, user, settings)
    query_term = (q or "").strip()
    uploads, pagination = await _filtered_uploads(
        session,
        query_term=query_term,
        status_filter=status,
        page=page,
        page_size=page_size,
    )
    metrics = await _upload_metrics(session)
    uploads_series = await _uploads_per_day(session, days=14)
    context.update(
        {
            "uploads": uploads,
            "pagination": pagination,
            "metrics": metrics,
            "uploads_series": uploads_series,
            "status_badge_class": _status_badge_class,
            "format_size": _format_size,
            "allowed_extensions": settings.allowed_upload_extension_list,
            "max_upload_mb": round(settings.max_upload_bytes / (1024 * 1024), 1),
            "success": None,
            "error": None,
            "status_filter_choices": list(UPLOAD_STATUS_FILTERS.keys()),
        }
    )
    return templates.TemplateResponse("uploads.html", context)


@router.post("/uploads")
async def uploads_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    context = _common_context(request, user, settings)
    success = None
    error = None

    try:
        upload = await UploadService(session, settings).store_upload(file, user)
        # Run Windmill trigger + dept emails in the background so the user
        # gets the page back immediately after the file is saved.
        background_tasks.add_task(
            UploadService.process_in_background,
            upload_id=upload.id,
            actor_id=user.id,
            actor_username=user.username,
            settings=settings,
        )
        success = {
            "filename": upload.original_filename,
            "upload_id": upload.id,
            "job_id": upload.windmill_job_id,
            "status": upload.status.value,
        }
    except HTTPException as exc:
        error = exc.detail
    except Exception:
        error = "Upload failed unexpectedly. Check application logs."

    uploads, pagination = await _filtered_uploads(
        session, query_term="", status_filter="all", page=1, page_size=25
    )
    metrics = await _upload_metrics(session)
    uploads_series = await _uploads_per_day(session, days=14)
    context.update(
        {
            "uploads": uploads,
            "pagination": pagination,
            "metrics": metrics,
            "uploads_series": uploads_series,
            "status_badge_class": _status_badge_class,
            "format_size": _format_size,
            "allowed_extensions": settings.allowed_upload_extension_list,
            "max_upload_mb": round(settings.max_upload_bytes / (1024 * 1024), 1),
            "success": success,
            "error": error,
            "status_filter_choices": list(UPLOAD_STATUS_FILTERS.keys()),
        }
    )
    return templates.TemplateResponse("uploads.html", context)


# ------------------------------------------------------------------
# /activity — dedicated audit-log viewer with filters & pagination
# ------------------------------------------------------------------
ACTIVITY_RANGE_CHOICES = ("24h", "7d", "30d", "all")


@router.get("/activity")
async def activity_page(
    request: Request,
    user: User = Depends(get_current_web_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    page: int = Query(1),
    page_size: int = Query(25),
    q: str | None = Query(None),
    action: str = Query("all"),
    range_: str = Query("7d", alias="range"),
):
    if page < 1:
        page = 1
    if page_size not in PAGE_SIZE_CHOICES:
        page_size = 25
    is_admin = user.role == Role.admin
    query_term = (q or "").strip()

    count_stmt = select(func.count(AuditLog.id))
    list_stmt = select(AuditLog).order_by(AuditLog.created_at.desc())

    if not is_admin:
        # Non-admins see only their own activity.
        count_stmt = count_stmt.where(AuditLog.actor_id == user.id)
        list_stmt = list_stmt.where(AuditLog.actor_id == user.id)

    if query_term:
        like = f"%{query_term}%"
        cond = or_(
            AuditLog.action.ilike(like),
            AuditLog.resource_type.ilike(like),
            AuditLog.resource_id.ilike(like),
            AuditLog.detail.ilike(like),
        )
        count_stmt = count_stmt.where(cond)
        list_stmt = list_stmt.where(cond)

    if action and action != "all":
        like = f"{action}%"
        count_stmt = count_stmt.where(AuditLog.action.ilike(like))
        list_stmt = list_stmt.where(AuditLog.action.ilike(like))

    range_map = {"24h": 1, "7d": 7, "30d": 30}
    if range_ in range_map:
        since = datetime.now(timezone.utc) - timedelta(days=range_map[range_])
        count_stmt = count_stmt.where(AuditLog.created_at >= since)
        list_stmt = list_stmt.where(AuditLog.created_at >= since)
    elif range_ not in ACTIVITY_RANGE_CHOICES:
        range_ = "7d"

    total = (await session.execute(count_stmt)).scalar_one() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size

    result = await session.execute(list_stmt.offset(offset).limit(page_size))
    items = list(result.scalars().all())

    # Distinct action prefixes ("file", "workflow", "auth", "user", …) for the dropdown.
    actions_stmt = select(AuditLog.action).distinct()
    if not is_admin:
        actions_stmt = actions_stmt.where(AuditLog.actor_id == user.id)
    raw_actions = (await session.execute(actions_stmt)).scalars().all()
    action_prefixes = sorted({a.split(".")[0] for a in raw_actions if a})

    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "first_index": offset + 1 if total else 0,
        "last_index": offset + len(items),
        "size_choices": PAGE_SIZE_CHOICES,
        "q": query_term,
        "action": action,
        "range": range_,
    }

    context = _common_context(request, user, settings)
    context.update(
        {
            "items": items,
            "pagination": pagination,
            "is_admin": is_admin,
            "action_prefixes": action_prefixes,
            "range_choices": ACTIVITY_RANGE_CHOICES,
        }
    )
    return templates.TemplateResponse("activity.html", context)


async def _build_phase_runs(
    session: AsyncSession,
    settings: Settings | None = None,
    limit: int = 12,
) -> list[dict]:
    """Reconstruct the 4-phase pipeline state for each of the most recent uploads.

    Phase order:  Store → Trigger → Split &amp; notify → Ingest.
    Status values per phase: passed, running, failed, blocked, pending.
    """
    uploads = (
        await session.execute(
            select(FileUpload).order_by(FileUpload.created_at.desc()).limit(limit)
        )
    ).scalars().all()

    if not uploads:
        return []

    upload_ids = [u.id for u in uploads]
    upload_id_strs = [str(uid) for uid in upload_ids]

    # Count ingested rows per upload, broken down by department.
    per_upload: dict[int, dict[str, int]] = {uid: {"finance": 0, "hr": 0, "sales": 0} for uid in upload_ids}
    dept_models = (("finance", FinanceData), ("hr", HRData), ("sales", SalesData))
    for dept, model in dept_models:
        result = await session.execute(
            select(model.source_upload_id, func.count(model.id))
            .where(model.source_upload_id.in_(upload_ids))
            .group_by(model.source_upload_id)
        )
        for upload_id, cnt in result.all():
            if upload_id in per_upload:
                per_upload[upload_id][dept] = int(cnt)

    # Email audit-log entries per upload — source of truth for "Split & notify".
    # Ingest audit-log entries per upload — source of truth for "Ingest"
    # (written by /api/v1/internal/ingest, so the row appears whether or not
    # any new rows were inserted — duplicates still count as a callback).
    email_logs: dict[int, list[AuditLog]] = {uid: [] for uid in upload_ids}
    ingest_logs: dict[int, AuditLog | None] = {uid: None for uid in upload_ids}
    log_result = await session.execute(
        select(AuditLog)
        .where(AuditLog.resource_type == "file_upload")
        .where(AuditLog.resource_id.in_(upload_id_strs))
        .where(AuditLog.action.in_(("email.dispatched", "email.failed", "ingest.received")))
        .order_by(AuditLog.created_at.asc())
    )
    for log in log_result.scalars().all():
        try:
            uid = int(log.resource_id)
        except (TypeError, ValueError):
            continue
        if uid not in email_logs:
            continue
        if log.action == "ingest.received":
            ingest_logs[uid] = log
        else:
            email_logs[uid].append(log)

    # Live Windmill job status for runs we think are still in flight
    # (triggered but ingest hasn't happened yet). Done in parallel with a short
    # timeout so an unreachable Windmill doesn't slow this page down.
    job_status_by_upload: dict[int, dict | None] = {}
    if settings is not None and not settings.windmill_mock:
        wm = WindmillService(settings)
        in_flight = [
            u for u in uploads
            if u.windmill_job_id
            and u.status.value == "workflow_triggered"
            and ingest_logs.get(u.id) is None
        ]
        if in_flight:
            statuses = await asyncio.gather(
                *(wm.get_job_status(u.windmill_job_id) for u in in_flight),
                return_exceptions=True,
            )
            for u, status_or_exc in zip(in_flight, statuses):
                if isinstance(status_or_exc, Exception):
                    job_status_by_upload[u.id] = {"state": "unknown", "reason": str(status_or_exc)}
                else:
                    job_status_by_upload[u.id] = status_or_exc

    runs: list[dict] = []
    for u in uploads:
        status_value = u.status.value
        failed = status_value == "workflow_failed"
        triggered = status_value == "workflow_triggered"
        breakdown = per_upload.get(u.id, {"finance": 0, "hr": 0, "sales": 0})
        ingested_rows = sum(breakdown.values())

        phases: list[dict] = []

        # 1. Store
        phases.append(
            {
                "key": "store",
                "name": "Store",
                "icon": "store",
                "status": "passed",
                "at": u.created_at,
                "detail": "File saved &amp; audit logged",
            }
        )

        # 2. Trigger
        if failed:
            phases.append(
                {
                    "key": "trigger",
                    "name": "Trigger",
                    "icon": "trigger",
                    "status": "failed",
                    "at": u.created_at,
                    "detail": "Windmill trigger failed",
                }
            )
        elif triggered:
            job_status_early = job_status_by_upload.get(u.id)
            if job_status_early and job_status_early.get("state") == "failure":
                phases.append(
                    {
                        "key": "trigger",
                        "name": "Trigger",
                        "icon": "trigger",
                        "status": "failed",
                        "at": u.created_at,
                        "detail": f"Windmill job failed: {job_status_early.get('error') or 'unknown error'}",
                    }
                )
            else:
                phases.append(
                    {
                        "key": "trigger",
                        "name": "Trigger",
                        "icon": "trigger",
                        "status": "passed",
                        "at": u.created_at,
                        "detail": f"Job {u.windmill_job_id}" if u.windmill_job_id else "Queued in Windmill",
                    }
                )
        else:
            phases.append(
                {
                    "key": "trigger",
                    "name": "Trigger",
                    "icon": "trigger",
                    "status": "pending",
                    "at": None,
                    "detail": "Awaiting trigger",
                }
            )

        # 3. Split & notify — driven by REAL email audit-log entries.
        # Per-dept "email.dispatched" or "email.failed" rows are recorded by
        # UploadService right after Windmill is triggered. If there are no
        # email log rows at all, we honestly say "Not attempted" rather than
        # pretending it ran.
        logs_for_upload = email_logs.get(u.id, [])
        email_sent = sum(1 for L in logs_for_upload if L.action == "email.dispatched")
        email_failed = sum(1 for L in logs_for_upload if L.action == "email.failed")
        email_total = email_sent + email_failed
        last_error = next(
            (L.detail for L in reversed(logs_for_upload) if L.action == "email.failed"),
            None,
        )

        if failed:
            phase3_status = "blocked"
            phase3_detail = "Skipped — trigger failed"
        elif email_total == 0:
            if triggered:
                phase3_status = "running"
                phase3_detail = "Waiting on department notifications…"
            else:
                phase3_status = "pending"
                phase3_detail = "Waiting"
        elif email_failed and email_sent == 0:
            phase3_status = "failed"
            phase3_detail = (
                f"All {email_failed} notifications failed"
                + (f": {last_error}" if last_error else "")
            )
        elif email_failed and email_sent:
            phase3_status = "failed"
            phase3_detail = (
                f"{email_sent} sent, {email_failed} failed"
                + (f" · last error: {last_error}" if last_error else "")
            )
        else:
            phase3_status = "passed"
            phase3_detail = f"{email_sent} department notifications sent"
        phases.append(
            {
                "key": "split",
                "name": "Split &amp; notify",
                "icon": "split",
                "status": phase3_status,
                "at": None,
                "detail": phase3_detail,
            }
        )

        # 4. Ingest — driven by the /internal/ingest audit-log row plus, if
        # available, live Windmill job status. This tells us whether the
        # callback happened, how many rows we got, and (if not) whether
        # Windmill itself succeeded or failed.
        ingest_log = ingest_logs.get(u.id)
        job_status = job_status_by_upload.get(u.id)

        if failed:
            phase4_status = "blocked"
            phase4_detail = "Skipped — trigger failed"
        elif ingest_log is not None:
            # Callback definitively happened (whether or not new rows landed).
            phase4_status = "passed"
            if ingested_rows > 0:
                phase4_detail = f"{ingested_rows} rows ingested"
            else:
                phase4_detail = "Callback received — all rows were duplicates"
        elif ingested_rows > 0:
            # Rows landed before we started audit-logging ingest callbacks
            # (older uploads). Treat as passed.
            phase4_status = "passed"
            phase4_detail = f"{ingested_rows} rows ingested"
        elif job_status and job_status.get("state") == "failure":
            phase4_status = "failed"
            err = (job_status.get("error") or "unknown error")
            phase4_detail = f"Windmill job failed: {err}"
        elif job_status and job_status.get("state") == "success":
            # Windmill says it finished but no ingest callback arrived → real bug.
            phase4_status = "failed"
            phase4_detail = (
                "Windmill job succeeded but never called /api/v1/internal/ingest — "
                "check the flow's HTTP step (URL / token / worker network)."
            )
        elif job_status and job_status.get("state") in ("running", "queued"):
            phase4_status = "running"
            phase4_detail = f"Windmill job is {job_status.get('state')}…"
        elif job_status and job_status.get("state") == "unknown":
            phase4_status = "running"
            phase4_detail = f"Status unknown: {job_status.get('reason')}"
        elif triggered:
            phase4_status = "running"
            phase4_detail = "Awaiting ingest callback"
        else:
            phase4_status = "pending"
            phase4_detail = "Waiting"

        phases.append(
            {
                "key": "ingest",
                "name": "Ingest",
                "icon": "ingest",
                "status": phase4_status,
                "at": ingest_log.created_at if ingest_log else None,
                "detail": phase4_detail,
            }
        )

        # Overall status of the run
        phase_states = [p["status"] for p in phases]
        if failed or "failed" in phase_states:
            overall = "failed"
        elif all(s == "passed" for s in phase_states):
            overall = "passed"
        elif "running" in phase_states or triggered:
            overall = "running"
        else:
            overall = "pending"

        runs.append(
            {
                "upload": u,
                "phases": phases,
                "breakdown": breakdown,
                "ingested_rows": ingested_rows,
                "overall": overall,
            }
        )

    return runs


def _windmill_urls(settings: Settings) -> tuple[str, str]:
    dashboard_url = (
        f"{settings.windmill_public_url.rstrip('/')}"
        f"/apps/get/{settings.windmill_dashboard_path}"
    )
    flow_url = (
        f"{settings.windmill_public_url.rstrip('/')}"
        f"/runs/{quote(settings.windmill_workflow_path, safe='')}"
    )
    return dashboard_url, flow_url


@router.get("/workflows")
async def workflows(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    dashboard_url, flow_url = _windmill_urls(settings)
    context = _common_context(request, user, settings)
    metrics = await _upload_metrics(session)
    ingest_series = await _ingest_per_day(session, days=14)
    context.update(
        {
            "windmill_dashboard_url": dashboard_url,
            "windmill_flow_url": flow_url,
            "windmill_live_url": "/workflows/live",
            "metrics": metrics,
            "ingest_series": ingest_series,
            "windmill_workflow_path": settings.windmill_workflow_path,
            "windmill_workspace": settings.windmill_workspace,
        }
    )
    return templates.TemplateResponse("workflows.html", context)


@router.get("/workflows/live")
async def workflows_live(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    settings: Settings = Depends(get_settings),
):
    dashboard_url, flow_url = _windmill_urls(settings)
    context = _common_context(request, user, settings)
    context.update(
        {
            "windmill_dashboard_url": dashboard_url,
            "windmill_flow_url": flow_url,
            "windmill_workflow_path": settings.windmill_workflow_path,
            "windmill_workspace": settings.windmill_workspace,
        }
    )
    return templates.TemplateResponse("workflows_live.html", context)


# ------------------------------------------------------------------
# /smtp — admin-only SMTP diagnostics page
# ------------------------------------------------------------------
def _smtp_context(request: Request, user: User, settings: Settings, result: dict | None) -> dict:
    smtp = SmtpService(settings)
    context = _common_context(request, user, settings)
    context.update(
        {
            "smtp_config_status": smtp.config_status(),
            "smtp_is_configured": smtp.is_configured(),
            "result": result,
            "default_test_recipient": settings.smtp_from or settings.smtp_username or "",
        }
    )
    return context


@router.get("/smtp")
async def smtp_page(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    settings: Settings = Depends(get_settings),
):
    return templates.TemplateResponse(
        "smtp.html", _smtp_context(request, user, settings, result=None)
    )


@router.post("/smtp/test-connection")
async def smtp_test_connection(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    settings: Settings = Depends(get_settings),
):
    smtp = SmtpService(settings)
    result = await smtp.test_connection()
    result["kind"] = "connection"
    return templates.TemplateResponse(
        "smtp.html", _smtp_context(request, user, settings, result=result)
    )


@router.post("/smtp/test-send")
async def smtp_test_send(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    settings: Settings = Depends(get_settings),
    recipient: str = Form(...),
):
    smtp = SmtpService(settings)
    result = await smtp.send_test_email(recipient)
    result["kind"] = "send"
    result["recipient"] = recipient
    return templates.TemplateResponse(
        "smtp.html", _smtp_context(request, user, settings, result=result)
    )


async def _pipeline_live_context(session: AsyncSession, settings: Settings) -> dict:
    """Shared context for the full /pipeline page and the /pipeline/refresh partial."""
    runs = await _build_phase_runs(session, settings=settings, limit=12)
    summary = {
        "total": len(runs),
        "passed": sum(1 for r in runs if r["overall"] == "passed"),
        "running": sum(1 for r in runs if r["overall"] == "running"),
        "failed": sum(1 for r in runs if r["overall"] == "failed"),
        "pending": sum(1 for r in runs if r["overall"] == "pending"),
    }
    return {
        "runs": runs,
        "latest": runs[0] if runs else None,
        "history": runs[1:] if len(runs) > 1 else [],
        "summary": summary,
        "format_size": _format_size,
        "status_badge_class": _status_badge_class,
    }


@router.get("/pipeline")
async def pipeline_phases(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    live = await _pipeline_live_context(session, settings)
    dashboard_url, flow_url = _windmill_urls(settings)
    metrics = await _upload_metrics(session)

    # Surface ingest config so admins can sanity-check what the Windmill flow
    # is supposed to call back to.
    masked_token = (
        settings.ingest_token[:4] + "…" + settings.ingest_token[-2:]
        if settings.ingest_token and len(settings.ingest_token) > 8
        else "(short or unset)"
    )

    context = _common_context(request, user, settings)
    context.update(live)
    context.update(
        {
            "metrics": metrics,
            "windmill_dashboard_url": dashboard_url,
            "windmill_flow_url": flow_url,
            "windmill_workflow_path": settings.windmill_workflow_path,
            "ingest_callback_url": settings.ingest_callback_url,
            "ingest_token_mask": masked_token,
            "windmill_mock": settings.windmill_mock,
        }
    )
    return templates.TemplateResponse("pipeline.html", context)


@router.get("/pipeline/refresh")
async def pipeline_refresh(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    """HTML partial used by the pipeline page for AJAX live-updates."""
    live = await _pipeline_live_context(session, settings)
    context = _common_context(request, user, settings)
    context.update(live)
    return templates.TemplateResponse("_pipeline_live.html", context)
