from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from minince.infrastructure.database.connection import SessionLocal
from minince.infrastructure.drivers import get_driver
from minince.infrastructure.repositories.backup_repository import BackupRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.shared.exceptions import DeviceConnectionError


class BackupService:
    def __init__(self, db=None) -> None:
        self._db = db or SessionLocal()

    def create_backup(
        self,
        device_id: int,
        created_by: str = "system",
        backup_type: str = "MANUAL",
        save_to_file: bool = True,
    ) -> dict[str, Any]:
        device_repo = DeviceRepository(self._db)
        backup_repo = BackupRepository(self._db)

        device = device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceConnectionError(f"Device {device_id} not found")

        driver = get_driver(
            vendor=device.vendor,
            host=device.management_ip,
            port=device.port,
            username=device.username,
            password=device.decrypted_password if hasattr(device, 'decrypted_password') else "",
        )

        driver.test_connection()
        config_content = driver.get_running_config()

        if not config_content:
            raise DeviceConnectionError(f"Failed to get configuration from device {device_id}")

        file_path = None
        if save_to_file:
            backup_dir = Path("backups") / datetime.utcnow().strftime("%Y%m")
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_path = backup_dir / f"{device.name}_{timestamp}.cfg"
            file_path.write_text(config_content, encoding="utf-8")

        backup = backup_repo.create(
            device_id=device_id,
            config_content=config_content,
            backup_type=backup_type,
            created_by=created_by,
            file_path=str(file_path) if file_path else None,
        )

        return {
            "backup_id": backup.id,
            "device_id": device_id,
            "device_name": device.name,
            "backup_type": backup_type,
            "checksum": backup.checksum,
            "file_path": str(file_path) if file_path else None,
            "created_at": backup.created_at.isoformat(),
            "config_size": len(config_content),
        }

    def get_backup(self, backup_id: int) -> dict[str, Any] | None:
        backup_repo = BackupRepository(self._db)
        backup = backup_repo.get_by_id(backup_id)
        if backup is None:
            return None

        return self._backup_to_dict(backup)

    def list_device_backups(self, device_id: int) -> list[dict[str, Any]]:
        backup_repo = BackupRepository(self._db)
        backups = backup_repo.list_by_device(device_id)
        return [self._backup_to_dict(b) for b in backups]

    def restore_backup(
        self,
        backup_id: int,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            backup_repo = BackupRepository(self._db)
            backup = backup_repo.get_by_id(backup_id)
            if backup is None:
                raise DeviceConnectionError(f"Backup {backup_id} not found")

            return {
                "status": "PENDING_CONFIRMATION",
                "backup_id": backup_id,
                "message": "Restore requires confirmation. Set confirmed=True to proceed.",
                "config_size": len(backup.config_content),
                "checksum": backup.checksum,
            }

        backup_repo = BackupRepository(self._db)
        device_repo = DeviceRepository(self._db)

        backup = backup_repo.get_by_id(backup_id)
        if backup is None:
            raise DeviceConnectionError(f"Backup {backup_id} not found")

        device = device_repo.get_by_id(backup.device_id)
        if device is None:
            raise DeviceConnectionError(f"Device {backup.device_id} not found")

        driver = get_driver(
            vendor=device.vendor,
            host=device.management_ip,
            port=device.port,
            username=device.username,
            password=device.decrypted_password if hasattr(device, 'decrypted_password') else "",
        )

        driver.test_connection()

        result = driver.apply_config(backup.config_content) if hasattr(driver, 'apply_config') else False

        restore_backup_record = backup_repo.restore_from_backup(
            backup_id=backup_id,
            restore_content=backup.config_content,
            created_by="system",
        )

        return {
            "status": "RESTORED" if result else "FAILED",
            "backup_id": backup_id,
            "restore_record_id": restore_backup_record.id,
            "device_id": device.id,
            "device_name": device.name,
            "config_restored": result,
        }

    def delete_backup(self, backup_id: int) -> bool:
        backup_repo = BackupRepository(self._db)
        return backup_repo.delete(backup_id)

    def verify_backup_integrity(self, backup_id: int) -> dict[str, Any]:
        backup_repo = BackupRepository(self._db)
        backup = backup_repo.get_by_id(backup_id)
        if backup is None:
            return {"valid": False, "error": "Backup not found"}

        computed_checksum = hashlib.sha256(backup.config_content.encode()).hexdigest()
        is_valid = computed_checksum == backup.checksum

        return {
            "valid": is_valid,
            "backup_id": backup_id,
            "stored_checksum": backup.checksum,
            "computed_checksum": computed_checksum,
            "match": is_valid,
        }

    def _backup_to_dict(self, backup: Any) -> dict[str, Any]:
        return {
            "id": backup.id,
            "device_id": backup.device_id,
            "backup_type": backup.backup_type,
            "config_size": len(backup.config_content),
            "checksum": backup.checksum,
            "file_path": backup.file_path,
            "created_by": backup.created_by,
            "created_at": backup.created_at.isoformat() if backup.created_at else None,
        }
