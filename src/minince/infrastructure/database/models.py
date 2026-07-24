from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from minince.infrastructure.database.connection import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    management_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(default=22)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=True)
    connection_type: Mapped[str] = mapped_column(String(50), default="SSH")
    status: Mapped[str] = mapped_column(String(50), default="INACTIVE")
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ConfigTask(Base, TimestampMixin):
    __tablename__ = "config_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    device_id: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    original_request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    structured_intent: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    generated_commands: Mapped[list[str]] = mapped_column(JSON, nullable=True)
    execution_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    verification_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskStep(Base, TimestampMixin):
    __tablename__ = "task_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConfigTemplate(Base, TimestampMixin):
    __tablename__ = "config_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), nullable=False)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    template_content: Mapped[str] = mapped_column(String, nullable=False)
    variable_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class ConfigBackup(Base, TimestampMixin):
    __tablename__ = "config_backups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(nullable=False, index=True)
    backup_type: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)
    config_content: Mapped[str] = mapped_column(String, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    restore_from_id: Mapped[int | None] = mapped_column(nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
