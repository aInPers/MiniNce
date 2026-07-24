from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from minince.infrastructure.database.models import ConfigBackup


class BackupRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        device_id: int,
        config_content: str,
        backup_type: str = "MANUAL",
        created_by: str = "system",
        file_path: str | None = None,
    ) -> ConfigBackup:
        checksum = hashlib.sha256(config_content.encode()).hexdigest()

        backup = ConfigBackup(
            device_id=device_id,
            backup_type=backup_type,
            config_content=config_content,
            checksum=checksum,
            file_path=file_path,
            created_by=created_by,
        )
        self._db.add(backup)
        self._db.commit()
        self._db.refresh(backup)
        return backup

    def get_by_id(self, backup_id: int) -> ConfigBackup | None:
        return self._db.query(ConfigBackup).filter(ConfigBackup.id == backup_id).first()

    def get_latest_by_device(self, device_id: int) -> ConfigBackup | None:
        return (
            self._db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == device_id)
            .order_by(ConfigBackup.created_at.desc())
            .first()
        )

    def list_by_device(
        self,
        device_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConfigBackup]:
        return (
            self._db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == device_id)
            .order_by(ConfigBackup.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def delete(self, backup_id: int) -> bool:
        backup = self.get_by_id(backup_id)
        if backup is None:
            return False
        self._db.delete(backup)
        self._db.commit()
        return True

    def restore_from_backup(
        self,
        backup_id: int,
        restore_content: str,
        created_by: str = "system",
    ) -> ConfigBackup:
        original = self.get_by_id(backup_id)

        return self.create(
            device_id=original.device_id if original else 0,
            config_content=restore_content,
            backup_type="RESTORE",
            created_by=created_by,
            file_path=None,
        )

    def count_by_device(self, device_id: int) -> int:
        return (
            self._db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == device_id)
            .count()
        )
