from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository


def get_device_repository(db: Session = ...) -> DeviceRepository:
    return DeviceRepository(db)


def get_task_repository(db: Session = ...) -> TaskRepository:
    return TaskRepository(db)


def provide_db() -> Generator[Session, None, None]:
    yield from get_db()
