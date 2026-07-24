from __future__ import annotations

import pytest

from minince.infrastructure.drivers.huawei_vrp.command_generator import HuaweiVRPCommandGenerator
from minince.shared.enums import RiskLevel


class TestHuaweiVRPCommandGeneratorVLAN:
    def setup_method(self) -> None:
        self.generator = HuaweiVRPCommandGenerator()

    def test_create_vlan_new(self) -> None:
        intent = {
            "operation": "create",
            "vlan_id": 100,
            "name": "MANAGEMENT",
            "description": "Management VLAN",
            "device_id": 1,
        }
        plan = self.generator.generate_vlan_commands(intent)

        assert plan.feature == "VLAN"
        assert plan.changed is True
        assert plan.risk_level == RiskLevel.LOW
        assert len(plan.commands) > 0
        assert plan.commands[0] == "vlan 100"
        assert " name MANAGEMENT" in plan.commands
        assert " description Management VLAN" in plan.commands
        assert "quit" in plan.commands
        assert "display vlan 100" in plan.verify_commands

    def test_create_vlan_idempotent(self) -> None:
        intent = {
            "operation": "create",
            "vlan_id": 100,
            "name": "MANAGEMENT",
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"vlan_id": 100, "name": "MANAGEMENT", "description": ""},
        }
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is False
        assert len(plan.commands) == 0

    def test_create_vlan_exists_with_different_name(self) -> None:
        intent = {
            "operation": "create",
            "vlan_id": 100,
            "name": "NEW_NAME",
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"vlan_id": 100, "name": "OLD_NAME", "description": ""},
        }
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is True
        assert "vlan 100" in plan.commands
        assert " name NEW_NAME" in plan.commands

    def test_update_vlan(self) -> None:
        intent = {
            "operation": "update",
            "vlan_id": 200,
            "name": "UPDATED",
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"vlan_id": 200, "name": "OLD", "description": ""},
        }
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is True
        assert plan.risk_level == RiskLevel.MEDIUM
        assert "vlan 200" in plan.commands
        assert " name UPDATED" in plan.commands

    def test_update_vlan_no_change(self) -> None:
        intent = {
            "operation": "update",
            "vlan_id": 200,
            "name": "SAME",
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"vlan_id": 200, "name": "SAME", "description": ""},
        }
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is False
        assert len(plan.commands) == 0

    def test_update_vlan_not_exists(self) -> None:
        intent = {
            "operation": "update",
            "vlan_id": 300,
            "name": "NEW",
            "device_id": 1,
        }
        current_state = {"exists": False, "data": {}}
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is True
        assert "vlan 300" in plan.commands
        assert len(plan.warnings) > 0

    def test_delete_vlan_exists(self) -> None:
        intent = {
            "operation": "delete",
            "vlan_id": 400,
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"vlan_id": 400, "name": "DELETE_ME"},
        }
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is True
        assert plan.risk_level == RiskLevel.HIGH
        assert "undo vlan 400" in plan.commands
        assert len(plan.warnings) > 0

    def test_delete_vlan_not_exists(self) -> None:
        intent = {
            "operation": "delete",
            "vlan_id": 500,
            "device_id": 1,
        }
        current_state = {"exists": False, "data": {}}
        plan = self.generator.generate_vlan_commands(intent, current_state)

        assert plan.changed is False
        assert len(plan.commands) == 0

    def test_vlan_steps(self) -> None:
        intent = {
            "operation": "create",
            "vlan_id": 10,
            "name": "TEST",
            "device_id": 1,
        }
        plan = self.generator.generate_vlan_commands(intent)

        assert len(plan.steps) > 0
        step_names = [s.name for s in plan.steps]
        assert "create_vlan" in step_names
        assert "set_vlan_name" in step_names
        assert "exit_vlan_view" in step_names

    def test_vlan_to_dict(self) -> None:
        intent = {
            "operation": "create",
            "vlan_id": 10,
            "name": "TEST",
            "device_id": 1,
        }
        plan = self.generator.generate_vlan_commands(intent)
        d = plan.to_dict()

        assert d["feature"] == "VLAN"
        assert d["risk_level"] == "LOW"
        assert "commands" in d
        assert "steps" in d


class TestHuaweiVRPCommandGeneratorInterface:
    def setup_method(self) -> None:
        self.generator = HuaweiVRPCommandGenerator()

    def test_configure_interface_description(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Uplink to Core",
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.feature == "INTERFACE"
        assert plan.changed is True
        assert "interface GigabitEthernet0/0/1" in plan.commands
        assert " description Uplink to Core" in plan.commands
        assert "quit" in plan.commands

    def test_configure_interface_admin_down(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/2",
            "admin_up": False,
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {"admin_up": True}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.changed is True
        assert plan.risk_level == RiskLevel.HIGH
        assert " shutdown" in plan.commands

    def test_configure_interface_admin_up(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/3",
            "admin_up": True,
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {"admin_up": False}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.changed is True
        assert " undo shutdown" in plan.commands

    def test_configure_access_interface(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/4",
            "link_type": "access",
            "access_vlan": 100,
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.changed is True
        assert " port link-type access" in plan.commands
        assert " port default vlan 100" in plan.commands

    def test_configure_trunk_interface(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/5",
            "link_type": "trunk",
            "trunk_allowed_vlans": [10, 20, 30],
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.changed is True
        assert plan.risk_level == RiskLevel.MEDIUM
        assert " port link-type trunk" in plan.commands
        assert " port trunk allow-pass vlan 10,20,30" in plan.commands

    def test_interface_idempotent(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Same desc",
            "device_id": 1,
        }
        current_state = {
            "exists": True,
            "data": {"description": "Same desc"},
        }
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert plan.changed is False
        assert len(plan.commands) == 0

    def test_interface_steps(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/1",
            "description": "Test",
            "device_id": 1,
        }
        plan = self.generator.generate_interface_commands(intent)

        assert len(plan.steps) > 0
        step_names = [s.name for s in plan.steps]
        assert "enter_interface_view" in step_names
        assert "set_description" in step_names
        assert "exit_interface_view" in step_names

    def test_interface_warning_on_shutdown(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/1",
            "admin_up": False,
            "device_id": 1,
        }
        current_state = {"exists": True, "data": {"admin_up": True}}
        plan = self.generator.generate_interface_commands(intent, current_state)

        assert len(plan.warnings) > 0
        assert "Disabling interface" in plan.warnings[0]

    def test_interface_verify_commands(self) -> None:
        intent = {
            "interface_name": "GigabitEthernet0/0/1",
            "device_id": 1,
        }
        plan = self.generator.generate_interface_commands(intent)

        assert "display current-configuration interface GigabitEthernet0/0/1" in plan.verify_commands