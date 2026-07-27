from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.application.services.device_service import DeviceService
from minince.config import settings
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import DeviceNotFoundError, ValidationError

router = APIRouter(prefix="/canvas", tags=["canvas"])

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


def _create_service(db: Session) -> DeviceService:
    return DeviceService(
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
        encryption=EncryptionManager(),
    )


@router.get("", response_class=HTMLResponse, response_model=None)
async def canvas_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """渲染拖拽画布页。"""
    service = _create_service(db)
    canvas_devices = service.list_canvas_devices()
    palette_devices = service.list_palette_devices()

    env = get_jinja_env()
    template = env.get_template("canvas.html")
    html = template.render(
        request=request,
        app_name=settings.app_name,
        canvas_devices=canvas_devices,
        palette_devices=palette_devices,
        active_page="canvas",
    )
    return HTMLResponse(content=html)


def _device_to_dict(device: object) -> dict[str, object]:
    return {
        "id": device.id,
        "name": device.name,
        "management_ip": device.management_ip,
        "vendor": device.vendor,
        "device_type": device.device_type,
        "canvas_x": device.canvas_x,
        "canvas_y": device.canvas_y,
        "status": device.status,
    }


@router.get("/api/devices", response_class=JSONResponse)
async def canvas_list_devices(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """返回画布设备与设备列表(用于前端刷新)。"""
    service = _create_service(db)
    return {
        "canvas_devices": [_device_to_dict(d) for d in service.list_canvas_devices()],
        "palette_devices": [_device_to_dict(d) for d in service.list_palette_devices()],
    }


@router.patch("/api/devices/{device_id}/position", response_class=JSONResponse)
async def canvas_update_position(
    device_id: int,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """更新设备画布坐标。"""
    canvas_x = payload.get("canvas_x")
    canvas_y = payload.get("canvas_y")
    if canvas_x is None or canvas_y is None:
        raise HTTPException(status_code=422, detail="canvas_x 和 canvas_y 必填")

    service = _create_service(db)
    try:
        device = service.update_device_position(
            device_id, int(canvas_x), int(canvas_y)
        )
        return {
            "success": True,
            "device": _device_to_dict(device),
        }
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/devices/{device_id}/position", response_class=JSONResponse)
async def canvas_set_position(
    device_id: int,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """从设备列表拖放到画布时设置初始坐标。"""
    canvas_x = payload.get("canvas_x")
    canvas_y = payload.get("canvas_y")
    if canvas_x is None or canvas_y is None:
        raise HTTPException(status_code=422, detail="canvas_x 和 canvas_y 必填")

    service = _create_service(db)
    try:
        device = service.update_device_position(
            device_id, int(canvas_x), int(canvas_y)
        )
        return {
            "success": True,
            "device": _device_to_dict(device),
        }
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/devices/{device_id}/remove", response_class=JSONResponse)
async def canvas_remove_device(
    device_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """将设备移出画布(清空坐标，保留设备记录)。"""
    service = _create_service(db)
    try:
        device = service.remove_from_canvas(device_id)
        return {
            "success": True,
            "device": _device_to_dict(device),
        }
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/api/devices/{device_id}/type", response_class=JSONResponse)
async def canvas_update_type(
    device_id: int,
    payload: dict[str, object] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """更新设备类型(ROUTER/SWITCH)。"""
    device_type = payload.get("device_type")
    if not device_type:
        raise HTTPException(status_code=422, detail="device_type 必填")

    service = _create_service(db)
    try:
        device = service.update_device_type(device_id, str(device_type))
        return {
            "success": True,
            "device": _device_to_dict(device),
        }
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
