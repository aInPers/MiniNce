from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.config import settings
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.device_repository import DeviceRepository

router = APIRouter()

TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")

_jinja_env: Environment | None = None


def get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=True,
            cache_size=0,
        )
    return _jinja_env


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    device_repo = DeviceRepository(db)

    device_count = device_repo.count_all()

    env = get_jinja_env()
    template = env.get_template("index.html")
    html = template.render(
        request=request,
        app_name=settings.app_name,
        app_version=settings.app_version,
        device_count=device_count,
        active_page="home",
    )
    return HTMLResponse(content=html)


@router.get("/health")
async def health_check() -> dict[str, object]:
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": settings.database_url.startswith("sqlite"),
    }
