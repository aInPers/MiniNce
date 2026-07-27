from __future__ import annotations

from typing import Any

from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.enums import DeviceType
from minince.shared.exceptions import DeviceNotFoundError, ValidationError


class DeviceService:
    def __init__(
        self,
        device_repo: DeviceRepository,
        audit_repo: AuditLogRepository,
        encryption: EncryptionManager | None = None,
    ) -> None:
        self._device_repo = device_repo
        self._audit_repo = audit_repo
        self._encryption = encryption or EncryptionManager()

    def create_device(
        self,
        name: str,
        hostname: str,
        management_ip: str,
        password: str,
        vendor: str,
        username: str,
        port: int = 22,
        platform: str | None = None,
        connection_type: str = "SSH",
        description: str | None = None,
        device_type: str = DeviceType.ROUTER.value,
    ) -> Any:
        existing = self._device_repo.get_by_name(name)
        if existing:
            raise ValidationError(f"Device with name '{name}' already exists")

        encrypted_password = self._encryption.encrypt(password)

        device = self._device_repo.create(
            name=name,
            hostname=hostname,
            management_ip=management_ip,
            encrypted_password=encrypted_password,
            vendor=vendor,
            username=username,
            port=port,
            platform=platform,
            connection_type=connection_type,
            description=description,
            device_type=device_type,
        )

        self._audit_repo.log(
            action="CREATE",
            resource_type="DEVICE",
            resource_id=str(device.id),
            actor="web",
            details={"name": name, "vendor": vendor, "device_type": device_type},
        )

        return device

    def update_device(
        self,
        device_id: int,
        **kwargs: Any,
    ) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        update_data = {}
        for key, value in kwargs.items():
            if key == "password" and value is not None:
                update_data["encrypted_password"] = self._encryption.encrypt(value)
            elif value is not None:
                update_data[key] = value

        updated = self._device_repo.update(device_id, **update_data)

        self._audit_repo.log(
            action="UPDATE",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={"changed_fields": list(update_data.keys())},
        )

        return updated

    def delete_device(self, device_id: int) -> bool:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        result = self._device_repo.delete_by_id(device_id)

        self._audit_repo.log(
            action="DELETE",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={"device_name": device.name},
        )

        return result

    def test_connection(self, device_id: int) -> dict[str, Any]:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        self._audit_repo.log(
            action="TEST_CONNECTION",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
        )

        return {
            "success": True,
            "message": f"Connection test for {device.name} (simulated)",
            "device_id": device_id,
        }

    def get_device(self, device_id: int) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)
        return device

    def list_devices(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[list[Any], int]:
        devices = self._device_repo.get_all(skip=skip, limit=limit)
        total = self._device_repo.count_all()
        return devices, total

    # ===== 画布用例 =====

    def list_canvas_devices(self) -> list[Any]:
        """返回已放置到画布上的设备。"""
        return self._device_repo.get_canvas_devices()

    def list_palette_devices(self) -> list[Any]:
        """返回未放置到画布上的设备(用于设备列表拖拽)。"""
        return self._device_repo.get_palette_devices()

    def update_device_position(
        self, device_id: int, canvas_x: int, canvas_y: int
    ) -> Any:
        """更新设备画布坐标，持久化到数据库。"""
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        updated = self._device_repo.update_position(device_id, canvas_x, canvas_y)

        self._audit_repo.log(
            action="UPDATE_POSITION",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={"canvas_x": canvas_x, "canvas_y": canvas_y},
        )
        return updated

    def remove_from_canvas(self, device_id: int) -> Any:
        """将设备移出画布(清空坐标)，设备记录保留。"""
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        updated = self._device_repo.clear_position(device_id)

        self._audit_repo.log(
            action="REMOVE_FROM_CANVAS",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={"device_name": device.name},
        )
        return updated

    def update_device_type(self, device_id: int, device_type: str) -> Any:
        """更新设备类型(ROUTER/SWITCH)。"""
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        valid_types = {t.value for t in DeviceType}
        if device_type not in valid_types:
            raise ValidationError(
                f"Invalid device_type '{device_type}', must be one of {valid_types}"
            )

        updated = self._device_repo.update_device_type(device_id, device_type)

        self._audit_repo.log(
            action="UPDATE_TYPE",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={"device_type": device_type},
        )
        return updated
