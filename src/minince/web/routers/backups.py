from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.backup_repository import BackupRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository

router = APIRouter(prefix="/backups", tags=["backups"])

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


@router.get("", response_class=HTMLResponse, response_model=None)
async def backup_list(
    request: Request,
    device_id: int | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    backup_repo = BackupRepository(db)
    device_repo = DeviceRepository(db)

    devices = device_repo.get_all()

    if device_id:
        backups = backup_repo.list_by_device(device_id, limit=200)
        total = len(backups)
    else:
        backups = backup_repo.get_all(limit=200)
        total = backup_repo.count_all()

    backup_list = []
    device_name_map = {d.id: d.name for d in devices}

    for b in backups:
        backup_list.append({
            "id": b.id,
            "device_id": b.device_id,
            "device_name": device_name_map.get(b.device_id, f"设备#{b.device_id}"),
            "backup_type": b.backup_type,
            "config_size": len(b.config_content) if b.config_content else 0,
            "checksum": b.checksum or "-",
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else "-",
            "created_by": b.created_by or "system",
        })

    html = render_template(
        "backups.html",
        request=request,
        backups=backup_list,
        total=total,
        devices=devices,
        selected_device_id=device_id,
        active_page="backups",
    )
    return HTMLResponse(content=html)


@router.post("/create", response_class=HTMLResponse, response_model=None)
async def backup_create(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    device_id = int(form.get("device_id", "0"))
    created_by = form.get("created_by", "admin")

    if not device_id:
        raise HTTPException(status_code=400, detail="设备ID不能为空")

    from minince.application.services.backup_service import BackupService

    service = BackupService(db)
    try:
        result = service.create_backup(
            device_id=device_id,
            created_by=created_by,
        )
        return RedirectResponse(url="/backups?message=备份创建成功", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/backups?error={str(e)}", status_code=303)


@router.post("/{backup_id}/restore", response_class=HTMLResponse, response_model=None)
async def backup_restore(
    backup_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    confirmed = form.get("confirmed") == "true"

    if not confirmed:
        return RedirectResponse(url=f"/backups?error=需要确认才能恢复备份", status_code=303)

    from minince.application.services.backup_service import BackupService

    service = BackupService(db)
    try:
        result = service.restore_backup(backup_id, confirmed=confirmed)
        return RedirectResponse(url="/backups?message=备份恢复命令已生成", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/backups?error={str(e)}", status_code=303)


@router.post("/{backup_id}/delete", response_class=HTMLResponse, response_model=None)
async def backup_delete(
    backup_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    backup_repo = BackupRepository(db)
    success = backup_repo.delete(backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="备份未找到")
    return RedirectResponse(url="/backups?message=备份已删除", status_code=303)
