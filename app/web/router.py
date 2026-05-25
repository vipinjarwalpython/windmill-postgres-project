from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
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
from app.services.upload_service import UploadService
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
    file: UploadFile = File(...),
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    context = _common_context(request, user, settings)
    success = None
    error = None

    try:
        upload = await UploadService(session, settings).upload_and_trigger(file, user)
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
