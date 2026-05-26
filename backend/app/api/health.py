"""健康检查。"""
from fastapi import APIRouter

from app import __version__
from app.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "env": settings.env, "version": __version__}
