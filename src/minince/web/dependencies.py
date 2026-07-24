from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from minince.application.services.device_service import DeviceService
from minince.application.services.task_executor import TaskExecutor
from minince.application.services.task_service import TaskService
from minince.application.services.template_service import TemplateService
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.repositories.template_repository import TemplateRepository
from minince.infrastructure.security.encryption import EncryptionManager


def get_device_repository(db: Annotated[Session, Depends(get_db)]) -> DeviceRepository:
    return DeviceRepository(db)


def get_task_repository(db: Annotated[Session, Depends(get_db)]) -> TaskRepository:
    return TaskRepository(db)


def get_template_repository(db: Annotated[Session, Depends(get_db)]) -> TemplateRepository:
    return TemplateRepository(db)


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


def get_task_service(
    db: Annotated[Session, Depends(get_db)],
) -> TaskService:
    return TaskService(
        task_repo=TaskRepository(db),
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
    )


def get_template_service(
    db: Annotated[Session, Depends(get_db)],
) -> TemplateService:
    return TemplateService(
        template_repo=TemplateRepository(db),
        audit_repo=AuditLogRepository(db),
    )


def get_task_executor(
    db: Annotated[Session, Depends(get_db)],
) -> TaskExecutor:
    return TaskExecutor(
        task_repo=TaskRepository(db),
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
        encryption=EncryptionManager(),
    )


def provide_db() -> Generator[Session, None, None]:
    yield from get_db()
