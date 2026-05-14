from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.department_data import DEPARTMENT_MODELS
from app.models.user import Role, User
from app.schemas.department import DepartmentDataResponse, DepartmentRow

router = APIRouter(prefix="/data", tags=["department-data"])


async def _fetch_department(session: AsyncSession, department: str) -> DepartmentDataResponse:
    model = DEPARTMENT_MODELS[department]
    result = await session.execute(select(model).order_by(model.id))
    rows = result.scalars().all()
    return DepartmentDataResponse(
        department=department,
        count=len(rows),
        rows=[DepartmentRow.model_validate(r) for r in rows],
    )


@router.get(
    "/me",
    response_model=DepartmentDataResponse,
    summary="Return rows for the caller's department (admin gets all departments combined)",
)
async def my_department_data(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role == Role.admin:
        combined: list[DepartmentRow] = []
        for dept in DEPARTMENT_MODELS:
            payload = await _fetch_department(session, dept)
            combined.extend(payload.rows)
        return DepartmentDataResponse(department="all", count=len(combined), rows=combined)

    department = current_user.role.value
    if department not in DEPARTMENT_MODELS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No department data for this role")
    return await _fetch_department(session, department)


@router.get(
    "/{department}",
    response_model=DepartmentDataResponse,
    summary="Return rows for a specific department (admin only, or the matching department user)",
)
async def department_data(
    department: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if department not in DEPARTMENT_MODELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown department")
    if current_user.role != Role.admin and current_user.role.value != department:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role ({current_user.role.value}) cannot read {department} data",
        )
    return await _fetch_department(session, department)
