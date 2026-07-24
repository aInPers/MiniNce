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


class TaskNotFoundError(MiniNCEError):
    def __init__(self, task_id: int | str) -> None:
        super().__init__(
            f"Task not found: {task_id}",
            code="TASK_NOT_FOUND",
            details={"task_id": task_id},
        )


class TaskStateError(MiniNCEError):
    def __init__(self, message: str, current_state: str, expected_state: str | None = None) -> None:
        super().__init__(
            message,
            code="TASK_STATE_ERROR",
            details={
                "current_state": current_state,
                "expected_state": expected_state,
            },
        )


class TaskExecutionError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="TASK_EXECUTION_ERROR", details=details)


class TemplateNotFoundError(MiniNCEError):
    def __init__(self, template_id: int | str) -> None:
        super().__init__(
            f"Template not found: {template_id}",
            code="TEMPLATE_NOT_FOUND",
            details={"template_id": template_id},
        )


class TemplateRenderError(MiniNCEError):
    def __init__(self, message: str, template_name: str) -> None:
        super().__init__(
            message,
            code="TEMPLATE_RENDER_ERROR",
            details={"template_name": template_name},
        )


class EncryptionError(MiniNCEError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="ENCRYPTION_ERROR")


class RiskBlockedError(MiniNCEError):
    def __init__(self, message: str, risk_level: str) -> None:
        super().__init__(
            message,
            code="RISK_BLOCKED",
            details={"risk_level": risk_level},
        )


class ConfigurationError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class RepositoryError(MiniNCEError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="REPOSITORY_ERROR", details=details)
