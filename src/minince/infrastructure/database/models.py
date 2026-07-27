from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
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
    # 设备类型：路由器/交换机，用于画布图标区分
    device_type: Mapped[str] = mapped_column(
        String(50), default="ROUTER", server_default="ROUTER", nullable=False
    )
    # 画布坐标：为空表示未放置到画布
    canvas_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canvas_y: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
