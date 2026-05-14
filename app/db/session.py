from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def create_database_schema() -> None:
    """Create tables for local development. Use Alembic migrations in production."""

    from sqlalchemy import text

    from app.models import (  # noqa: F401
        audit_log,
        department_data,
        department_settings,
        file_upload,
        user,
    )

    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM pg_type t "
                "JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = 'role' AND e.enumlabel = 'loan_officer'"
            )
        )
        if result.first() is not None:
            await conn.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS file_uploads CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            await conn.execute(text("DROP TYPE IF EXISTS role CASCADE"))

        await conn.run_sync(Base.metadata.create_all)
