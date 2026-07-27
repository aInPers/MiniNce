from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.PARTIAL)

    @property
    def is_active(self) -> bool:
        return self in (
            TaskStatus.DRAFT,
            TaskStatus.VALIDATING,
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.VERIFYING,
        )


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def requires_confirmation(self) -> bool:
        return self in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @property
    def severity_order(self) -> int:
        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        return order[self]


class DeviceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"
    MAINTENANCE = "MAINTENANCE"


class DeviceType(StrEnum):
    """设备类型：用于画布图标区分与拓扑展示。"""

    ROUTER = "ROUTER"
    SWITCH = "SWITCH"


class DeviceVendor(StrEnum):
    HUAWEI = "HUAWEI"
    CISCO = "CISCO"
    H3C = "H3C"
    JUNIPER = "JUNIPER"
    GENERIC = "GENERIC"


class ConnectionType(StrEnum):
    SSH = "SSH"
    TELNET = "TELNET"
    CONSOLE = "CONSOLE"


class TaskType(StrEnum):
    VLAN_CREATE = "VLAN_CREATE"
    VLAN_UPDATE = "VLAN_UPDATE"
    VLAN_DELETE = "VLAN_DELETE"
    INTERFACE_CONFIG = "INTERFACE_CONFIG"
    INTERFACE_VLAN = "INTERFACE_VLAN"
    CUSTOM = "CUSTOM"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
