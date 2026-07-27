from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from minince.infrastructure.database.connection import SessionLocal
from minince.infrastructure.repositories.device_repository import DeviceRepository

router = APIRouter(prefix="/template-config", tags=["template-config"])

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


def render_template(template_name: str, **kwargs: Any) -> str:
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)


@router.get("", response_class=HTMLResponse, response_model=None)
async def template_config_page(request: Request) -> HTMLResponse:
    """显示常用模板配置页面（VLAN / OSPF）。"""
    db = SessionLocal()
    try:
        device_repo = DeviceRepository(db)
        devices = device_repo.get_all()
    finally:
        db.close()

    html = render_template(
        "template_config.html",
        request=request,
        devices=devices,
        active_page="template_config",
    )
    return HTMLResponse(content=html)
