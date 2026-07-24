from __future__ import annotations

import pytest

from minince.infrastructure.ssh.base import SSHConfig
from minince.infrastructure.ssh.mock_connection import MockSSHConnection


class TestMockSSHConnection:
    def setup_method(self) -> None:
        config = SSHConfig(host="mock", port=22, username="admin", password="test")
        self.conn = MockSSHConnection(config)
        self.conn.connect()

    def test_connect_disconnect(self) -> None:
        assert self.conn.is_connected is True
        self.conn.disconnect()
        assert self.conn.is_connected is False

    def test_context_manager(self) -> None:
        config = SSHConfig(host="mock")
        with MockSSHConnection(config) as conn:
            assert conn.is_connected is True
        assert conn.is_connected is False

    def test_display_version(self) -> None:
        output = self.conn.send_command("display version")
        assert "Huawei" in output
        assert "VRP" in output

    def test_display_vlan_not_exists(self) -> None:
        output = self.conn.send_command("display vlan 999")
        assert "does not exist" in output.lower()

    def test_create_vlan(self) -> None:
        self.conn.send_command("system-view")
        self.conn.send_command("vlan 100")
        self.conn.send_command(" name TEST_VLAN")
        self.conn.send_command("quit")

        output = self.conn.send_command("display vlan 100")
        assert "VLAN ID: 100" in output
        assert "TEST_VLAN" in output

    def test_delete_vlan(self) -> None:
        self.conn.send_command("system-view")
        self.conn.send_command("vlan 200")
        self.conn.send_command("quit")

        self.conn.send_command("undo vlan 200")

        output = self.conn.send_command("display vlan 200")
        assert "does not exist" in output.lower()

    def test_configure_interface(self) -> None:
        self.conn.send_command("system-view")
        self.conn.send_command("interface GigabitEthernet0/0/1")
        self.conn.send_command(" description Uplink")
        self.conn.send_command(" port link-type access")
        self.conn.send_command(" port default vlan 100")
        self.conn.send_command("quit")

        output = self.conn.send_command("display interface GigabitEthernet0/0/1")
        assert "GigabitEthernet0/0/1" in output
        assert "access" in output.lower()

    def test_display_current_config(self) -> None:
        self.conn.send_command("system-view")
        self.conn.send_command("vlan 100")
        self.conn.send_command(" name TEST")
        self.conn.send_command("quit")

        output = self.conn.send_command("display current-configuration")
        assert "vlan batch" in output
        assert "100" in output

    def test_save_config(self) -> None:
        result = self.conn.save_config()
        assert "Save the configuration successfully" in result

    def test_send_config_set(self) -> None:
        commands = [
            "system-view",
            "vlan 300",
            " name CONFIG_TEST",
            "quit",
        ]
        result = self.conn.send_config_set(commands)
        assert "VLAN 300" in result

        output = self.conn.send_command("display vlan 300")
        assert "CONFIG_TEST" in output


class TestMockSSHConnectionVLAN:
    def setup_method(self) -> None:
        config = SSHConfig(host="mock")
        self.conn = MockSSHConnection(config)
        self.conn.connect()
        self.conn.send_command("system-view")

    def test_vlan_workflow(self) -> None:
        self.conn.send_command("vlan 10")
        self.conn.send_command("name=EXEC_TEST")

        output = self.conn.send_command("display vlan 10")
        assert "VLAN ID: 10" in output

    def test_multiple_vlans(self) -> None:
        for i in range(1, 5):
            self.conn.send_command(f"vlan {i * 10}")
            self.conn.send_command(f" name VLAN_{i}")
            self.conn.send_command("quit")
            self.conn.send_command("system-view")

        for i in range(1, 5):
            output = self.conn.send_command(f"display vlan {i * 10}")
            assert f"VLAN ID: {i * 10}" in output
            assert f"VLAN_{i}" in output
            self.conn.send_command("system-view")
            self.conn.send_command("quit")

    def test_vlan_description(self) -> None:
        self.conn.send_command("vlan 500")
        self.conn.send_command(" description Test description for VLAN 500")

        output = self.conn.send_command("display vlan 500")
        assert "VLAN ID: 500" in output
        assert "Test description" in output


class TestMockSSHConnectionInterface:
    def setup_method(self) -> None:
        config = SSHConfig(host="mock")
        self.conn = MockSSHConnection(config)
        self.conn.connect()
        self.conn.send_command("system-view")

    def test_interface_description(self) -> None:
        self.conn.send_command("interface GigabitEthernet0/0/1")
        self.conn.send_command(" description Test Interface")

        output = self.conn.send_command("display interface GigabitEthernet0/0/1")
        assert "Test Interface" in output

    def test_interface_admin_state(self) -> None:
        self.conn.send_command("interface GigabitEthernet0/0/2")
        self.conn.send_command(" shutdown")

        output = self.conn.send_command("display interface GigabitEthernet0/0/2")
        assert "line protocol is down" in output.lower()

    def test_interface_link_type(self) -> None:
        self.conn.send_command("interface GigabitEthernet0/0/3")
        self.conn.send_command(" port link-type trunk")

        output = self.conn.send_command("display interface GigabitEthernet0/0/3")
        assert "trunk" in output.lower()

    def test_trunk_allowed_vlans(self) -> None:
        self.conn.send_command("interface GigabitEthernet0/0/4")
        self.conn.send_command(" port link-type trunk")
        self.conn.send_command(" port trunk allow-pass vlan 10,20,30")

        output = self.conn.send_command("display interface GigabitEthernet0/0/4")
        assert "Trunk allowed VLANs" in output
