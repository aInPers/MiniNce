from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.repositories.template_repository import TemplateRepository

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db)) -> dict[str, object]:
    device_repo = DeviceRepository(db)
    task_repo = TaskRepository(db)
    template_repo = TemplateRepository(db)

    return {
        "devices": {
            "total": device_repo.count_all(),
            "active": device_repo.count_all(),
        },
        "tasks": {
            "total": task_repo.count_all(),
            "running": task_repo.count_all(status="RUNNING"),
            "succeeded": task_repo.count_all(status="SUCCEEDED"),
            "failed": task_repo.count_all(status="FAILED"),
        },
        "templates": {
            "total": template_repo.count_all(),
        },
    }


@router.get("/devices")
async def list_devices(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    device_repo = DeviceRepository(db)
    devices = device_repo.get_all(skip=skip, limit=limit)
    total = device_repo.count_all()
    return {
        "total": total,
        "items": [
            {
                "id": d.id,
                "name": d.name,
                "management_ip": d.management_ip,
                "port": d.port,
                "vendor": d.vendor,
                "status": d.status,
                "last_connected_at": str(d.last_connected_at) if d.last_connected_at else None,
            }
            for d in devices
        ],
    }


@router.get("/tasks")
async def list_tasks(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    task_repo = TaskRepository(db)
    tasks = task_repo.get_all(skip=skip, limit=limit, status=status)
    total = task_repo.count_all(status=status)
    return {
        "total": total,
        "items": [
            {
                "id": t.id,
                "task_number": t.task_number,
                "task_type": t.task_type,
                "device_id": t.device_id,
                "status": t.status,
                "risk_level": t.risk_level,
                "created_at": str(t.created_at),
            }
            for t in tasks
        ],
    }


@router.get("/templates")
async def list_templates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    template_repo = TemplateRepository(db)
    templates = template_repo.get_all(skip=skip, limit=limit)
    total = template_repo.count_all()
    return {
        "total": total,
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "vendor": t.vendor,
                "feature": t.feature,
                "version": t.version,
                "enabled": t.enabled,
            }
            for t in templates
        ],
    }


@router.post("/devices/{device_id}/backups")
async def create_device_backup(
    device_id: int,
    created_by: str = "system",
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.application.services.backup_service import BackupService

    service = BackupService(db)
    try:
        result = service.create_backup(
            device_id=device_id,
            created_by=created_by,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/backups")
async def list_backups(
    device_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.infrastructure.repositories.backup_repository import BackupRepository

    backup_repo = BackupRepository(db)
    if device_id:
        backups = backup_repo.list_by_device(device_id, limit=limit)
    else:
        from minince.infrastructure.database.models import ConfigBackup
        backups = db.query(ConfigBackup).order_by(ConfigBackup.created_at.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": b.id,
                "device_id": b.device_id,
                "backup_type": b.backup_type,
                "config_size": len(b.config_content),
                "checksum": b.checksum,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in backups
        ],
        "total": len(backups),
    }


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    confirmed: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.application.services.backup_service import BackupService

    service = BackupService(db)
    try:
        result = service.restore_backup(backup_id, confirmed=confirmed)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.infrastructure.repositories.backup_repository import BackupRepository

    backup_repo = BackupRepository(db)
    success = backup_repo.delete(backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"success": True, "backup_id": backup_id}


@router.post("/templates/{template_id}/render")
async def render_template(
    template_id: int,
    variables: dict[str, object] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.application.services.template_renderer import TemplateRenderer
    from minince.infrastructure.repositories.template_repository import TemplateRepository

    template_repo = TemplateRepository(db)
    template = template_repo.get_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    renderer = TemplateRenderer()
    variables = variables or {}

    try:
        rendered = renderer.render(
            template.template_content,
            variables,
            template.variable_schema,
        )
        return {
            "template_id": template_id,
            "template_name": template.name,
            "rendered_content": rendered,
            "variables_used": list(variables.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(str(e)))


@router.post("/templates/validate")
async def validate_template(
    template_content: str = Body(...),
    variable_schema: dict[str, object] | None = Body(default=None),
) -> dict[str, object]:
    from minince.application.services.template_renderer import TemplateRenderer

    renderer = TemplateRenderer()
    result = renderer.validate_template(template_content, variable_schema)
    return result


@router.get("/templates/{template_id}/variables")
async def get_template_variables(
    template_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from minince.application.services.template_renderer import TemplateRenderer
    from minince.infrastructure.repositories.template_repository import TemplateRepository

    template_repo = TemplateRepository(db)
    template = template_repo.get_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    renderer = TemplateRenderer()
    variables = renderer.get_template_variables(template.template_content)
    return {
        "template_id": template_id,
        "template_name": template.name,
        "template_variables": variables,
        "schema_variables": list(template.variable_schema.keys()) if template.variable_schema else [],
    }
