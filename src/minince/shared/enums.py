from __future__ import annotations

from enum import StrEnum


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
