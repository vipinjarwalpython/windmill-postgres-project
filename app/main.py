from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.seed import seed_demo_users, seed_department_settings
from app.db.session import create_database_schema
from app.middleware.exception_handler import register_exception_handlers
from app.middleware.request_id import RequestIdMiddleware


settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_database_schema()
    await seed_demo_users()
    await seed_department_settings()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="RBAC-protected FastAPI backend that stores uploads and triggers Windmill workflows.",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(api_router)


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "FastAPI Windmill RBAC API is running",
        "docs": "/docs",
        "health": "/api/v1/health/ready",
    }
