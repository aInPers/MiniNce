from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
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


class RiskLevel(str, Enum):
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


class DeviceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"
    MAINTENANCE = "MAINTENANCE"


class DeviceVendor(str, Enum):
    HUAWEI = "HUAWEI"
    CISCO = "CISCO"
    H3C = "H3C"
    JUNIPER = "JUNIPER"
    GENERIC = "GENERIC"


class ConnectionType(str, Enum):
    SSH = "SSH"
    TELNET = "TELNET"
    CONSOLE = "CONSOLE"


class TaskType(str, Enum):
    VLAN_CREATE = "VLAN_CREATE"
    VLAN_UPDATE = "VLAN_UPDATE"
    VLAN_DELETE = "VLAN_DELETE"
    INTERFACE_CONFIG = "INTERFACE_CONFIG"
    INTERFACE_VLAN = "INTERFACE_VLAN"
    CUSTOM = "CUSTOM"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
