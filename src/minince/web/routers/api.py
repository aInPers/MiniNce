from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.device_repository import DeviceRepository

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db)) -> dict[str, object]:
    device_repo = DeviceRepository(db)

    return {
        "devices": {
            "total": device_repo.count_all(),
            "active": device_repo.count_all(),
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
