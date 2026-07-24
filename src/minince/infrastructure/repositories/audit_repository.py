from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from minince.infrastructure.database.models import AuditLog
from minince.infrastructure.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository):
    def get_by_id(self, log_id: int) -> AuditLog | None:
        stmt = select(AuditLog).where(AuditLog.id == log_id)
        return self.scalar_one(stmt)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        actor: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[AuditLog]:
        stmt = select(AuditLog)
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(AuditLog.resource_id == resource_id)
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        return self.scalars(stmt)

    def count_all(
        self,
        actor: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        stmt = select(AuditLog)
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        return self.count(stmt)

    def create(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        self.add(log)
        self.commit()
        self.refresh(log)
        return log

    def log(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        return self.create(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
