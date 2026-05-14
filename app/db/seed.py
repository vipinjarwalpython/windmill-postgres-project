import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.department_settings import DepartmentSetting
from app.models.user import Role, User

logger = logging.getLogger(__name__)


DEMO_USERS = [
    ("admin", "admin1234", Role.admin),
    ("finance_user", "finance1234", Role.finance),
    ("hr_user", "hr1234", Role.hr),
    ("sales_user", "sales1234", Role.sales),
]


async def seed_demo_users() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User.username))
        existing_usernames = {row[0] for row in existing.all()}
        created: list[str] = []
        for username, password, role in DEMO_USERS:
            if username in existing_usernames:
                continue
            session.add(User(username=username, password_hash=hash_password(password), role=role))
            created.append(f"{username}:{role.value}")
        if created:
            await session.commit()
            logger.info("seeded_demo_users", extra={"created": ",".join(created)})


async def seed_department_settings() -> None:
    emails = get_settings().department_email_defaults
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(DepartmentSetting.department))
        existing_departments = {row[0] for row in existing.all()}
        created: list[str] = []
        for department, email in emails.items():
            if department in existing_departments:
                continue
            session.add(DepartmentSetting(department=department, email=email))
            created.append(f"{department}:{email}")
        if created:
            await session.commit()
            logger.info("seeded_department_settings", extra={"created": ",".join(created)})
