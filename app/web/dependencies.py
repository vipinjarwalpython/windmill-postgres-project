from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models.user import Role, User
from app.repositories.user_repository import UserRepository


SESSION_COOKIE_NAME = "session_token"


class RedirectToLogin(HTTPException):
    """Raised by web dependencies to short-circuit unauthenticated requests."""

    def __init__(self) -> None:
        super().__init__(status_code=302, detail="redirect_to_login")


async def _resolve_user(request: Request, session: AsyncSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except ValueError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = await UserRepository(session).get_by_username(username)
    if not user or not user.is_active:
        return None
    return user


async def get_current_web_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user = await _resolve_user(request, session)
    if user is None:
        raise RedirectToLogin()
    return user


async def get_optional_web_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    return await _resolve_user(request, session)


def require_web_roles(*allowed_roles: Role) -> Callable:
    async def checker(current_user: User = Depends(get_current_web_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="You do not have permission to view this page")
        return current_user

    return checker
