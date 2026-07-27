from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from minince.application.services.device_service import DeviceService
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager


def get_device_repository(db: Annotated[Session, Depends(get_db)]) -> DeviceRepository:
    return DeviceRepository(db)


def get_audit_repository(db: Annotated[Session, Depends(get_db)]) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_encryption_manager() -> EncryptionManager:
    return EncryptionManager()


def get_device_service(
    db: Annotated[Session, Depends(get_db)],
) -> DeviceService:
    return DeviceService(
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
        encryption=EncryptionManager(),
    )


def provide_db() -> Generator[Session, None, None]:
    yield from get_db()
