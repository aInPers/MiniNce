from __future__ import annotations

from typing import Any


class MiniNCEError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class DeviceConnectionError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="DEVICE_CONNECTION_ERROR", details=details)


class DeviceAuthenticationError(DeviceConnectionError):
    def __init__(self, message: str) -> None:
        MiniNCEError.__init__(self, message, code="DEVICE_AUTH_ERROR")


class DeviceNotFoundError(MiniNCEError):
    def __init__(self, device_id: int) -> None:
        super().__init__(
            f"Device not found: {device_id}",
            code="DEVICE_NOT_FOUND",
            details={"device_id": device_id},
        )


class EncryptionError(MiniNCEError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="ENCRYPTION_ERROR")


class ConfigurationError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class RepositoryError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="REPOSITORY_ERROR", details=details)
