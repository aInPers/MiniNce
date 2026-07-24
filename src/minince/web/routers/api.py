from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.repositories.template_repository import TemplateRepository
from minince.shared.exceptions import DeviceNotFoundError, TaskNotFoundError, ValidationError

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
