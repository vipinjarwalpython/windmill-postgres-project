from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FastAPI Windmill RBAC"
    environment: str = "local"
    log_level: str = "INFO"

    secret_key: str = Field(min_length=16)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/loan_db"

    storage_dir: Path = Path("/data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_upload_extensions: str = ".csv,.json,.txt,.pdf"

    windmill_base_url: str = "https://your-windmill-domain.com"
    windmill_public_url: str = "http://localhost:8080"
    windmill_workspace: str = "prod"
    windmill_token: str = ""
    windmill_workflow_path: str = "u/admin/loan_pipeline"
    windmill_dashboard_path: str = "u/admin/loan_dashboard"
    windmill_timeout_seconds: int = 20
    windmill_mock: bool = True

    ingest_token: str = "local-ingest-secret-change-me"
    ingest_callback_url: str = "http://api:8000/api/v1/internal/ingest"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    finance_email: str = "squirreltechnical@gmail.com"
    hr_email: str = "squirreltechnical@gmail.com"
    sales_email: str = "squirreltechnical@gmail.com"

    @property
    def department_email_defaults(self) -> dict[str, str]:
        return {
            "finance": self.finance_email,
            "hr": self.hr_email,
            "sales": self.sales_email,
        }

    @property
    def smtp_config(self) -> dict[str, object]:
        return {
            "host": self.smtp_host,
            "port": self.smtp_port,
            "username": self.smtp_username,
            "password": self.smtp_password,
            "from_addr": self.smtp_from or self.smtp_username,
        }

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_upload_extension_list(self) -> list[str]:
        return [item.strip().lower() for item in self.allowed_upload_extensions.split(",") if item.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
