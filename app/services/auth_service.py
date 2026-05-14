from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserCreate, UserLogin
from app.services.audit_service import AuditService


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    async def register(self, payload: UserCreate) -> User:
        existing = await self.users.get_by_username(payload.username)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

        user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            role=payload.role,
        )
        await self.users.create(user)
        await self.audit.record(
            action="user.registered",
            resource_type="user",
            actor_id=user.id,
            resource_id=str(user.id),
        )
        await self.session.commit()
        return user

    async def login(self, payload: UserLogin) -> str:
        user = await self.users.get_by_username(payload.username)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

        await self.audit.record(
            action="user.login",
            resource_type="user",
            actor_id=user.id,
            resource_id=str(user.id),
        )
        await self.session.commit()
        return create_access_token(subject=user.username, role=user.role.value, user_id=user.id)
