from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceFacts:
    hostname: str = ""
    model: str = ""
    firmware_version: str = ""
    vendor: str = ""
    serial_number: str = ""
    uptime: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "vendor": self.vendor,
            "serial_number": self.serial_number,
            "uptime": self.uptime,
        }


@dataclass
class ConnectionResult:
    success: bool
    message: str = ""
    response_time_ms: int = 0
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "response_time_ms": self.response_time_ms,
            "error_type": self.error_type,
        }


@dataclass
class CurrentState:
    feature: str
    exists: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "exists": self.exists,
            "data": self.data,
        }
