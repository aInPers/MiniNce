from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db)) -> dict[str, object]:
    device_repo = DeviceRepository(db)
    task_repo = TaskRepository(db)

    return {
        "devices": {
            "total": device_repo.count_all(),
        },
        "tasks": {
            "total": task_repo.count_all(),
            "running": task_repo.count_all(status="RUNNING"),
            "succeeded": task_repo.count_all(status="SUCCEEDED"),
            "failed": task_repo.count_all(status="FAILED"),
        },
    }
