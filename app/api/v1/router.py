from fastapi import APIRouter

from app.api.v1.routers import auth, data, health, internal, uploads


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(uploads.router)
api_router.include_router(data.router)
api_router.include_router(internal.router)
api_router.include_router(health.router)
