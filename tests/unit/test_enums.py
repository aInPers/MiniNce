from __future__ import annotations

import pytest

from minince.shared.enums import (
    ConnectionType,
    DeviceStatus,
    DeviceVendor,
    RiskLevel,
    StepStatus,
    TaskStatus,
    TaskType,
)


class TestTaskStatus:
    def test_task_status_values(self) -> None:
        assert TaskStatus.DRAFT.value == "DRAFT"
        assert TaskStatus.VALIDATING.value == "VALIDATING"
        assert TaskStatus.READY.value == "READY"
        assert TaskStatus.RUNNING.value == "RUNNING"
        assert TaskStatus.VERIFYING.value == "VERIFYING"
        assert TaskStatus.SUCCEEDED.value == "SUCCEEDED"
        assert TaskStatus.FAILED.value == "FAILED"
        assert TaskStatus.PARTIAL.value == "PARTIAL"

    def test_is_terminal(self) -> None:
        assert TaskStatus.SUCCEEDED.is_terminal is True
        assert TaskStatus.FAILED.is_terminal is True
        assert TaskStatus.PARTIAL.is_terminal is True
        assert TaskStatus.DRAFT.is_terminal is False
        assert TaskStatus.RUNNING.is_terminal is False

    def test_is_active(self) -> None:
        assert TaskStatus.DRAFT.is_active is True
        assert TaskStatus.VALIDATING.is_active is True
        assert TaskStatus.READY.is_active is True
        assert TaskStatus.RUNNING.is_active is True
        assert TaskStatus.VERIFYING.is_active is True
        assert TaskStatus.SUCCEEDED.is_active is False
        assert TaskStatus.FAILED.is_active is False


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


class TestTaskType:
    def test_task_type_values(self) -> None:
        assert TaskType.VLAN_CREATE.value == "VLAN_CREATE"
        assert TaskType.VLAN_UPDATE.value == "VLAN_UPDATE"
        assert TaskType.VLAN_DELETE.value == "VLAN_DELETE"
        assert TaskType.INTERFACE_CONFIG.value == "INTERFACE_CONFIG"
        assert TaskType.INTERFACE_VLAN.value == "INTERFACE_VLAN"
        assert TaskType.CUSTOM.value == "CUSTOM"


class TestStepStatus:
    def test_step_status_values(self) -> None:
        assert StepStatus.PENDING.value == "PENDING"
        assert StepStatus.RUNNING.value == "RUNNING"
        assert StepStatus.SUCCEEDED.value == "SUCCEEDED"
        assert StepStatus.FAILED.value == "FAILED"
        assert StepStatus.SKIPPED.value == "SKIPPED"
