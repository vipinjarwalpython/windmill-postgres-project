from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.department_data import DEPARTMENT_MODELS
from app.models.file_upload import FileUpload
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
        token = await AuthService(session).login(UserLogin(username=username, password=password))
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


@router.get("/dashboard")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_web_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    page: int = Query(1),
    page_size: int = Query(25),
):
    if page < 1:
        page = 1
    context = _common_context(request, user, settings)
    is_admin = user.role == Role.admin
    department = None if is_admin else user.role.value

    department_rows: list = []
    pagination = None
    if department and department in DEPARTMENT_MODELS:
        if page_size not in PAGE_SIZE_CHOICES:
            page_size = 25
        model = DEPARTMENT_MODELS[department]

        total = (await session.execute(select(func.count(model.id)))).scalar_one()
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size

        result = await session.execute(
            select(model)
            .order_by(model.created_at.desc(), model.id.desc())
            .offset(offset)
            .limit(page_size)
        )
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
        }

    context.update(
        {
            "can_upload": is_admin,
            "is_admin": is_admin,
            "department": department,
            "department_rows": department_rows,
            "pagination": pagination,
        }
    )
    return templates.TemplateResponse("dashboard.html", context)


async def _recent_uploads(session: AsyncSession, limit: int = 10) -> list[FileUpload]:
    result = await session.execute(
        select(FileUpload).order_by(FileUpload.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


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


@router.get("/uploads")
async def uploads_page(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    context = _common_context(request, user, settings)
    uploads = await _recent_uploads(session)
    context.update(
        {
            "uploads": uploads,
            "status_badge_class": _status_badge_class,
            "format_size": _format_size,
            "allowed_extensions": settings.allowed_upload_extension_list,
            "max_upload_mb": round(settings.max_upload_bytes / (1024 * 1024), 1),
            "success": None,
            "error": None,
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

    uploads = await _recent_uploads(session)
    context.update(
        {
            "uploads": uploads,
            "status_badge_class": _status_badge_class,
            "format_size": _format_size,
            "allowed_extensions": settings.allowed_upload_extension_list,
            "max_upload_mb": round(settings.max_upload_bytes / (1024 * 1024), 1),
            "success": success,
            "error": error,
        }
    )
    return templates.TemplateResponse("uploads.html", context)


@router.get("/workflows")
async def workflows(
    request: Request,
    user: User = Depends(require_web_roles(Role.admin)),
    settings: Settings = Depends(get_settings),
):
    dashboard_url = (
        f"{settings.windmill_public_url.rstrip('/')}"
        f"/apps/get/{settings.windmill_dashboard_path}"
    )
    flow_url = (
        f"{settings.windmill_public_url.rstrip('/')}"
        f"/runs/{quote(settings.windmill_workflow_path, safe='')}"
    )
    context = _common_context(request, user, settings)
    context["windmill_dashboard_url"] = dashboard_url
    context["windmill_flow_url"] = flow_url
    return templates.TemplateResponse("workflows.html", context)
