from __future__ import annotations

import pytest

from minince.shared.exceptions import (
    ConfigurationError,
    DeviceAuthenticationError,
    DeviceConnectionError,
    DeviceNotFoundError,
    EncryptionError,
    MiniNCEError,
    RepositoryError,
    RiskBlockedError,
    TaskExecutionError,
    TaskNotFoundError,
    TaskStateError,
    TemplateNotFoundError,
    TemplateRenderError,
    ValidationError,
)


class TestMiniNCEError:
    def test_base_error(self) -> None:
        error = MiniNCEError("test error")
        assert error.message == "test error"
        assert error.code == "UNKNOWN_ERROR"
        assert error.details == {}

    def test_error_with_details(self) -> None:
        error = MiniNCEError("test", code="CUSTOM_CODE", details={"key": "value"})
        assert error.code == "CUSTOM_CODE"
        assert error.details == {"key": "value"}

    def test_to_dict(self) -> None:
        error = MiniNCEError("test", code="TEST_CODE", details={"a": 1})
        result = error.to_dict()
        assert result == {
            "code": "TEST_CODE",
            "message": "test",
            "details": {"a": 1},
        }


class TestValidationError:
    def test_validation_error(self) -> None:
        error = ValidationError("Invalid input")
        assert error.code == "VALIDATION_ERROR"
        assert error.message == "Invalid input"


class TestDeviceErrors:
    def test_device_connection_error(self) -> None:
        error = DeviceConnectionError("Connection failed")
        assert error.code == "DEVICE_CONNECTION_ERROR"

    def test_device_auth_error(self) -> None:
        error = DeviceAuthenticationError("Auth failed")
        assert error.code == "DEVICE_AUTH_ERROR"

    def test_device_not_found_error(self) -> None:
        error = DeviceNotFoundError(1)
        assert error.code == "DEVICE_NOT_FOUND"
        assert error.details["device_id"] == 1


class TestTaskErrors:
    def test_task_not_found_error(self) -> None:
        error = TaskNotFoundError("TASK-001")
        assert error.code == "TASK_NOT_FOUND"
        assert error.details["task_id"] == "TASK-001"

    def test_task_state_error(self) -> None:
        error = TaskStateError("Invalid state", current_state="DRAFT", expected_state="READY")
        assert error.code == "TASK_STATE_ERROR"
        assert error.details["current_state"] == "DRAFT"
        assert error.details["expected_state"] == "READY"

    def test_task_execution_error(self) -> None:
        error = TaskExecutionError("Execution failed")
        assert error.code == "TASK_EXECUTION_ERROR"


class TestTemplateErrors:
    def test_template_not_found_error(self) -> None:
        error = TemplateNotFoundError(5)
        assert error.code == "TEMPLATE_NOT_FOUND"

    def test_template_render_error(self) -> None:
        error = TemplateRenderError("Render failed", "test_template")
        assert error.code == "TEMPLATE_RENDER_ERROR"
        assert error.details["template_name"] == "test_template"


class TestOtherErrors:
    def test_encryption_error(self) -> None:
        error = EncryptionError("Encrypt failed")
        assert error.code == "ENCRYPTION_ERROR"

    def test_risk_blocked_error(self) -> None:
        error = RiskBlockedError("High risk operation", "HIGH")
        assert error.code == "RISK_BLOCKED"
        assert error.details["risk_level"] == "HIGH"

    def test_configuration_error(self) -> None:
        error = ConfigurationError("Config error")
        assert error.code == "CONFIGURATION_ERROR"

    def test_repository_error(self) -> None:
        error = RepositoryError("DB error")
        assert error.code == "REPOSITORY_ERROR"
