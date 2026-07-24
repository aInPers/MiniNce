from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.application.services.device_service import DeviceService
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import DeviceNotFoundError, ValidationError

router = APIRouter(prefix="/devices", tags=["devices"])

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


def _create_service(db: Session) -> DeviceService:
    return DeviceService(
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
        encryption=EncryptionManager(),
    )


@router.get("", response_class=HTMLResponse, response_model=None)
async def device_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_service(db)
    devices, total = service.list_devices()
    html = render_template(
        "devices.html",
        request=request,
        devices=devices,
        total=total,
        active_page="devices",
    )
    return HTMLResponse(content=html)


@router.get("/new", response_class=HTMLResponse, response_model=None)
async def device_new(request: Request) -> HTMLResponse:
    html = render_template(
        "device_form.html",
        request=request,
        device=None,
        action="create",
        active_page="devices",
    )
    return HTMLResponse(content=html)


@router.post("", response_class=HTMLResponse, response_model=None)
async def device_create(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_service(db)
    try:
        service.create_device(
            name=form.get("name", ""),
            hostname=form.get("hostname", ""),
            management_ip=form.get("management_ip", ""),
            password=form.get("password", ""),
            vendor=form.get("vendor", "HUAWEI"),
            username=form.get("username", "admin"),
            port=int(form.get("port", "22")),
            platform=form.get("platform") or None,
            connection_type=form.get("connection_type", "SSH"),
            description=form.get("description") or None,
        )
        return RedirectResponse(url="/devices", status_code=303)
    except ValidationError as e:
        html = render_template(
            "device_form.html",
            request=request,
            device=form,
            action="create",
            error=str(e),
            active_page="devices",
        )
        return HTMLResponse(content=html, status_code=400)


@router.get("/{device_id}", response_class=HTMLResponse, response_model=None)
async def device_detail(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_service(db)
    try:
        device = service.get_device(device_id)
        html = render_template(
            "device_detail.html",
            request=request,
            device=device,
            active_page="devices",
        )
        return HTMLResponse(content=html)
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{device_id}/edit", response_class=HTMLResponse, response_model=None)
async def device_edit(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_service(db)
    try:
        device = service.get_device(device_id)
        html = render_template(
            "device_form.html",
            request=request,
            device=device,
            action="update",
            active_page="devices",
        )
        return HTMLResponse(content=html)
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{device_id}", response_class=HTMLResponse, response_model=None)
async def device_update(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_service(db)
    update_data: dict[str, str] = {}
    for field in ["name", "hostname", "management_ip", "password", "username", "vendor", "platform", "connection_type", "description"]:
        val = form.get(field)
        if val is not None and val != "":
            update_data[field] = str(val)
    port = form.get("port")
    if port:
        update_data["port"] = str(int(str(port)))

    try:
        service.update_device(device_id, **update_data)
        return RedirectResponse(url=f"/devices/{device_id}", status_code=303)
    except (DeviceNotFoundError, ValidationError) as e:
        device = service.get_device(device_id)
        html = render_template(
            "device_form.html",
            request=request,
            device=device,
            action="update",
            error=str(e),
            active_page="devices",
        )
        return HTMLResponse(content=html, status_code=400)


@router.post("/{device_id}/delete", response_class=HTMLResponse, response_model=None)
async def device_delete(
    device_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_service(db)
    try:
        service.delete_device(device_id)
        return RedirectResponse(url="/devices", status_code=303)
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{device_id}/test", response_class=HTMLResponse, response_model=None)
async def device_test_connection(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_service(db)
    try:
        result = service.test_connection(device_id)
        device = service.get_device(device_id)
        html = render_template(
            "device_detail.html",
            request=request,
            device=device,
            test_result=result,
            active_page="devices",
        )
        return HTMLResponse(content=html)
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
