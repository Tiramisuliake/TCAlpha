"""健康检查。"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "env": settings.env, "version": "0.1.0"}
