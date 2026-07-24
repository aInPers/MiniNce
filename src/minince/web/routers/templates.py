from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.application.services.template_service import TemplateService
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.template_repository import TemplateRepository
from minince.shared.exceptions import TemplateNotFoundError, ValidationError

router = APIRouter(prefix="/templates", tags=["templates"])

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


def render_template(template_name: str, **kwargs) -> str:
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)


def _create_template_service(db: Session) -> TemplateService:
    return TemplateService(
        template_repo=TemplateRepository(db),
        audit_repo=AuditLogRepository(db),
    )


@router.get("", response_class=HTMLResponse, response_model=None)
async def template_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_template_service(db)
    templates, total = service.list_templates()
    html = render_template(
        "templates.html",
        request=request,
        templates=templates,
        total=total,
        active_page="templates",
    )
    return HTMLResponse(content=html)


@router.get("/new", response_class=HTMLResponse, response_model=None)
async def template_new(request: Request) -> HTMLResponse:
    html = render_template(
        "template_form.html",
        request=request,
        template=None,
        action="create",
        active_page="templates",
    )
    return HTMLResponse(content=html)


@router.post("", response_class=HTMLResponse, response_model=None)
async def template_create(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_template_service(db)
    try:
        service.create_template(
            name=form.get("name", ""),
            vendor=form.get("vendor", "HUAWEI"),
            feature=form.get("feature", "VLAN"),
            template_content=form.get("template_content", ""),
            version=form.get("version", "1.0"),
            variable_schema=None,
            enabled=form.get("enabled") == "on",
        )
        return RedirectResponse(url="/templates", status_code=303)
    except ValidationError as e:
        html = render_template(
            "template_form.html",
            request=request,
            template=form,
            action="create",
            error=str(e),
            active_page="templates",
        )
        return HTMLResponse(content=html, status_code=400)


@router.get("/{template_id}/edit", response_class=HTMLResponse, response_model=None)
async def template_edit(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_template_service(db)
    try:
        template = service.get_template(template_id)
        html = render_template(
            "template_form.html",
            request=request,
            template=template,
            action="update",
            active_page="templates",
        )
        return HTMLResponse(content=html)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{template_id}", response_class=HTMLResponse, response_model=None)
async def template_update(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_template_service(db)
    update_data: dict[str, str] = {}
    for field in ["name", "vendor", "feature", "template_content", "version"]:
        val = form.get(field)
        if val is not None and val != "":
            update_data[field] = str(val)
    enabled = form.get("enabled")
    if enabled is not None:
        update_data["enabled"] = "on" if str(enabled) == "on" else "off"

    try:
        service.update_template(template_id, **update_data)
        return RedirectResponse(url="/templates", status_code=303)
    except (TemplateNotFoundError, ValidationError) as e:
        template = service.get_template(template_id)
        html = render_template(
            "template_form.html",
            request=request,
            template=template,
            action="update",
            error=str(e),
            active_page="templates",
        )
        return HTMLResponse(content=html, status_code=400)


@router.post("/{template_id}/delete", response_class=HTMLResponse, response_model=None)
async def template_delete(
    template_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_template_service(db)
    try:
        service.delete_template(template_id)
        return RedirectResponse(url="/templates", status_code=303)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
