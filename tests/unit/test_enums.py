from __future__ import annotations

from minince.shared.enums import (
    ConnectionType,
    DeviceStatus,
    DeviceVendor,
    RiskLevel,
)


class TestRiskLevel:
    def test_risk_level_values(self) -> None:
        assert RiskLevel.LOW.value == "LOW"
        assert RiskLevel.MEDIUM.value == "MEDIUM"
        assert RiskLevel.HIGH.value == "HIGH"
        assert RiskLevel.CRITICAL.value == "CRITICAL"

    def test_requires_confirmation(self) -> None:
        assert RiskLevel.LOW.requires_confirmation is False
        assert RiskLevel.MEDIUM.requires_confirmation is False
        assert RiskLevel.HIGH.requires_confirmation is True
        assert RiskLevel.CRITICAL.requires_confirmation is True

    def test_severity_order(self) -> None:
        assert RiskLevel.LOW.severity_order < RiskLevel.MEDIUM.severity_order
        assert RiskLevel.MEDIUM.severity_order < RiskLevel.HIGH.severity_order
        assert RiskLevel.HIGH.severity_order < RiskLevel.CRITICAL.severity_order


class TestDeviceStatus:
    def test_device_status_values(self) -> None:
        assert DeviceStatus.ACTIVE.value == "ACTIVE"
        assert DeviceStatus.INACTIVE.value == "INACTIVE"
        assert DeviceStatus.ERROR.value == "ERROR"
        assert DeviceStatus.MAINTENANCE.value == "MAINTENANCE"


class TestDeviceVendor:
    def test_device_vendor_values(self) -> None:
        assert DeviceVendor.HUAWEI.value == "HUAWEI"
        assert DeviceVendor.CISCO.value == "CISCO"
        assert DeviceVendor.H3C.value == "H3C"
        assert DeviceVendor.JUNIPER.value == "JUNIPER"
        assert DeviceVendor.GENERIC.value == "GENERIC"


class TestConnectionType:
    def test_connection_type_values(self) -> None:
        assert ConnectionType.SSH.value == "SSH"
        assert ConnectionType.TELNET.value == "TELNET"
        assert ConnectionType.CONSOLE.value == "CONSOLE"
