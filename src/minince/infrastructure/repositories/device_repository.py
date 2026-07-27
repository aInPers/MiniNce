from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from minince.infrastructure.database.models import Device
from minince.infrastructure.repositories.base import BaseRepository


class DeviceRepository(BaseRepository):
    def get_by_id(self, device_id: int) -> Device | None:
        stmt = select(Device).where(Device.id == device_id)
        return self.scalar_one(stmt)

    def get_by_name(self, name: str) -> Device | None:
        stmt = select(Device).where(Device.name == name)
        return self.scalar_one(stmt)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[Device]:
        stmt = select(Device).offset(skip).limit(limit)
        return self.scalars(stmt)

    def count_all(self) -> int:
        stmt = select(Device)
        return self.count(stmt)

    def create(
        self,
        name: str,
        hostname: str,
        management_ip: str,
        encrypted_password: str,
        vendor: str,
        username: str,
        port: int = 22,
        platform: str | None = None,
        connection_type: str = "SSH",
        description: str | None = None,
        device_type: str = "ROUTER",
    ) -> Device:
        device = Device(
            name=name,
            hostname=hostname,
            management_ip=management_ip,
            port=port,
            username=username,
            encrypted_password=encrypted_password,
            vendor=vendor,
            platform=platform,
            connection_type=connection_type,
            status="INACTIVE",
            description=description,
            device_type=device_type,
        )
        self.add(device)
        self.commit()
        self.refresh(device)
        return device

    def update(self, device_id: int, **kwargs: Any) -> Device | None:
        device = self.get_by_id(device_id)
        if device is None:
            return None

        for key, value in kwargs.items():
            if hasattr(device, key) and value is not None:
                setattr(device, key, value)

        device.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(device)
        return device

    def delete_by_id(self, device_id: int) -> bool:
        device = self.get_by_id(device_id)
        if device is None:
            return False

        self.delete(device)
        self.commit()
        return True

    def update_status(self, device_id: int, status: str) -> Device | None:
        return self.update(device_id, status=status)

    def update_last_connected(self, device_id: int) -> Device | None:
        return self.update(device_id, last_connected_at=datetime.utcnow())

    def update_position(
        self, device_id: int, canvas_x: int, canvas_y: int
    ) -> Device | None:
        """更新设备在画布上的坐标。"""
        return self.update(device_id, canvas_x=canvas_x, canvas_y=canvas_y)

    def clear_position(self, device_id: int) -> Device | None:
        """清除设备画布坐标，将其移出画布。"""
        device = self.get_by_id(device_id)
        if device is None:
            return None
        device.canvas_x = None
        device.canvas_y = None
        device.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(device)
        return device

    def update_device_type(self, device_id: int, device_type: str) -> Device | None:
        """更新设备类型(ROUTER/SWITCH)。"""
        return self.update(device_id, device_type=device_type)

    def get_canvas_devices(self) -> list[Device]:
        """返回已放置到画布上的设备(坐标不为空)。"""
        stmt = select(Device).where(Device.canvas_x.is_not(None))
        return self.scalars(stmt)

    def get_palette_devices(self) -> list[Device]:
        """返回未放置到画布上的设备(坐标为空)，用于设备列表拖拽。"""
        stmt = select(Device).where(Device.canvas_x.is_(None))
        return self.scalars(stmt)
