from __future__ import annotations

from minince.shared.exceptions import (
    ConfigurationError,
    DeviceAuthenticationError,
    DeviceConnectionError,
    DeviceNotFoundError,
    EncryptionError,
    MiniNCEError,
    RepositoryError,
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


class TestOtherErrors:
    def test_encryption_error(self) -> None:
        error = EncryptionError("Encrypt failed")
        assert error.code == "ENCRYPTION_ERROR"

    def test_configuration_error(self) -> None:
        error = ConfigurationError("Config error")
        assert error.code == "CONFIGURATION_ERROR"

    def test_repository_error(self) -> None:
        error = RepositoryError("DB error")
        assert error.code == "REPOSITORY_ERROR"
