from __future__ import annotations

import pytest

from minince.infrastructure.drivers.huawei_vrp.driver import HuaweiVRPDriver
from minince.shared.enums import RiskLevel


class TestHuaweiVRPDriverConnection:
    def test_connection_success(self) -> None:
        driver = HuaweiVRPDriver(host="192.168.1.1", port=22, username="admin", password="test")
        result = driver.test_connection()

        assert result.success is True
        assert "192.168.1.1" in result.message

    def test_connection_no_host(self) -> None:
        driver = HuaweiVRPDriver()
        result = driver.test_connection()

        assert result.success is False
        assert result.error_type == "NO_HOST"

    def test_get_facts_when_connected(self) -> None:
        driver = HuaweiVRPDriver(host="192.168.1.1", port=22, username="admin", password="test")
        driver.test_connection()
        facts = driver.get_facts()

        assert facts.vendor == "HUAWEI"
        assert facts.hostname
        assert facts.model

    def test_get_facts_default(self) -> None:
        driver = HuaweiVRPDriver()
        facts = driver.get_facts()

        assert facts.hostname == ""
        assert facts.model == ""


class TestHuaweiVRPDriverVLAN:
    def setup_method(self) -> None:
        self.driver = HuaweiVRPDriver(host="192.168.1.1", port=22, username="admin", password="test")
        self.driver.test_connection()

    def test_get_current_state_vlan_not_exists(self) -> None:
        intent = {"feature": "VLAN", "vlan_id": 100}
        state = self.driver.get_current_state(intent)

        assert state.feature == "VLAN"
        assert state.exists is False

    def test_build_plan_create_vlan(self) -> None:
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 100,
            "name": "TEST",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)

        assert plan.feature == "VLAN"
        assert plan.changed is True
        assert "vlan 100" in plan.commands

    def test_apply_plan_create_vlan(self) -> None:
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 100,
            "name": "TEST",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True
        assert len(result.command_outputs) > 0

    def test_verify_vlan_after_create(self) -> None:
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 200,
            "name": "VERIFY_TEST",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)
        result = self.driver.verify(intent)

        assert result.success is True

    def test_verify_vlan_delete(self) -> None:
        intent_create = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 300,
            "name": "TO_DELETE",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        intent_delete = {
            "feature": "VLAN",
            "operation": "delete",
            "vlan_id": 300,
            "device_id": 1,
        }
        state2 = self.driver.get_current_state(intent_delete)
        plan2 = self.driver.build_plan(intent_delete, state2)
        self.driver.apply_plan(plan2)
        result = self.driver.verify(intent_delete)

        assert result.success is True

    def test_idempotent_create(self) -> None:
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 100,
            "name": "TEST",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        state2 = self.driver.get_current_state(intent)
        plan2 = self.driver.build_plan(intent, state2)
        result = self.driver.apply_plan(plan2)

        assert plan2.changed is False
        assert result.success is True


class TestHuaweiVRPDriverInterface:
    def setup_method(self) -> None:
        self.driver = HuaweiVRPDriver(host="192.168.1.1", port=22, username="admin", password="test")
        self.driver.test_connection()

    def test_get_current_state_interface(self) -> None:
        intent = {"feature": "INTERFACE", "interface_name": "GigabitEthernet0/0/1"}
        state = self.driver.get_current_state(intent)

        assert state.feature == "INTERFACE"

    def test_build_plan_configure_interface(self) -> None:
        intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Uplink",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)

        assert plan.feature == "INTERFACE"
        assert plan.changed is True
        assert "interface GigabitEthernet0/0/1" in plan.commands

    def test_apply_and_verify_interface(self) -> None:
        intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Test Interface",
            "admin_up": True,
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True

        verify_result = self.driver.verify(intent)
        assert verify_result.success is True

    def test_configure_access_interface(self) -> None:
        intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/2",
            "link_type": "access",
            "access_vlan": 100,
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True

        verify_result = self.driver.verify(intent)
        assert verify_result.success is True

    def test_configure_trunk_interface(self) -> None:
        intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/3",
            "link_type": "trunk",
            "trunk_allowed_vlans": [10, 20],
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True

        verify_result = self.driver.verify(intent)
        assert verify_result.success is True

    def test_interface_idempotent(self) -> None:
        intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Same Config",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        state2 = self.driver.get_current_state(intent)
        plan2 = self.driver.build_plan(intent, state2)

        assert plan2.changed is False


class TestHuaweiVRPDriverUnsupported:
    def setup_method(self) -> None:
        self.driver = HuaweiVRPDriver(host="192.168.1.1", port=22, username="admin", password="test")
        self.driver.test_connection()

    def test_unsupported_feature(self) -> None:
        intent = {"feature": "OSPF", "process_id": 1}
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)

        assert plan.changed is False
        assert len(plan.warnings) > 0
        assert "Unsupported feature" in plan.warnings[0]