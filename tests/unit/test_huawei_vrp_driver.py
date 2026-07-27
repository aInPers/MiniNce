from __future__ import annotations

import pytest

from minince.infrastructure.drivers.huawei_vrp.huawei_device import HuaweiDevice
from minince.infrastructure.ssh.base import SSHConfig
from minince.infrastructure.ssh.mock_connection import MockSSHConnection
from minince.shared.enums import ConnectionType, RiskLevel


class TestHuaweiDeviceConnection:
    def test_connection_success(self) -> None:
        driver = HuaweiDevice(host="mock:192.168.1.1", port=22, username="admin", password="test")
        result = driver.connect(ConnectionType.SSH)

        assert result.success is True
        assert "mock:192.168.1.1" in result.message

    def test_connection_no_host(self) -> None:
        driver = HuaweiDevice()
        result = driver.connect(ConnectionType.SSH)

        assert result.success is False
        assert result.error_type == "NO_HOST"

    def test_get_facts_when_connected(self) -> None:
        driver = HuaweiDevice(host="mock:192.168.1.1", port=22, username="admin", password="test")
        driver.connect(ConnectionType.SSH)
        facts = driver.get_facts()

        assert facts.vendor == "HUAWEI"
        assert facts.hostname
        assert facts.model

    def test_get_facts_default(self) -> None:
        driver = HuaweiDevice()
        facts = driver.get_facts()

        # 默认使用 MockSSHConnection，_ensure_connected 会自动连接
        assert facts.vendor == "HUAWEI"
        assert facts.hostname


class TestHuaweiDeviceVLAN:
    def setup_method(self) -> None:
        self.driver = HuaweiDevice(host="mock:192.168.1.1", port=22, username="admin", password="test")
        self.driver.connect(ConnectionType.SSH)

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

    def test_delete_vlan_with_vlanif(self) -> None:
        """测试删除带 VLANIF 接口的 VLAN。

        场景：VLAN 关联了 L3 接口（Vlanif），直接 undo vlan 会报错
              "The VLAN has a L3 interface. Please delete it first."
        预期：driver 应先执行 undo interface VlanifX，再执行 undo vlan X
        """
        # 1. 创建 VLAN
        intent_create = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 400,
            "name": "WITH_VLANIF",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        # 2. 通过 SSH 直接创建 Vlanif 接口（模拟用户手动创建 L3 接口）
        self.driver._ssh_connection.send_command("system-view")
        self.driver._ssh_connection.send_command("interface Vlanif400")
        self.driver._ssh_connection.send_command("quit")
        self.driver._ssh_connection.send_command("return")

        # 3. 验证 get_current_state 检测到 VLANIF
        state_with_vlanif = self.driver.get_current_state({
            "feature": "VLAN",
            "vlan_id": 400,
        })
        assert state_with_vlanif.exists is True
        assert state_with_vlanif.data.get("has_vlanif") is True

        # 4. 构建删除计划，应包含 undo interface Vlanif400
        intent_delete = {
            "feature": "VLAN",
            "operation": "delete",
            "vlan_id": 400,
            "device_id": 1,
        }
        plan_delete = self.driver.build_plan(intent_delete, state_with_vlanif)

        assert plan_delete.changed is True
        assert "undo interface Vlanif400" in plan_delete.commands
        assert "undo vlan 400" in plan_delete.commands
        # 验证 Vlanif 删除命令在 VLAN 删除命令之前
        vlanif_idx = plan_delete.commands.index("undo interface Vlanif400")
        vlan_idx = plan_delete.commands.index("undo vlan 400")
        assert vlanif_idx < vlan_idx

        # 5. 执行删除并验证
        result = self.driver.apply_plan(plan_delete)
        assert result.success is True

        verify_result = self.driver.verify(intent_delete)
        assert verify_result.success is True

    def test_delete_vlan_without_vlanif(self) -> None:
        """测试删除不带 VLANIF 的 VLAN，不应生成 undo interface Vlanif 命令。"""
        intent_create = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 500,
            "name": "NO_VLANIF",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        state_no_vlanif = self.driver.get_current_state({
            "feature": "VLAN",
            "vlan_id": 500,
        })
        assert state_no_vlanif.exists is True
        assert state_no_vlanif.data.get("has_vlanif") is False

        intent_delete = {
            "feature": "VLAN",
            "operation": "delete",
            "vlan_id": 500,
            "device_id": 1,
        }
        plan_delete = self.driver.build_plan(intent_delete, state_no_vlanif)

        assert plan_delete.changed is True
        assert "undo interface Vlanif500" not in plan_delete.commands
        assert "undo vlan 500" in plan_delete.commands

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


class TestHuaweiDeviceInterface:
    def setup_method(self) -> None:
        self.driver = HuaweiDevice(host="mock:192.168.1.1", port=22, username="admin", password="test")
        self.driver.connect(ConnectionType.SSH)

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


class TestHuaweiDeviceUnsupported:
    def setup_method(self) -> None:
        self.driver = HuaweiDevice(host="mock:192.168.1.1", port=22, username="admin", password="test")
        self.driver.connect(ConnectionType.SSH)

    def test_unsupported_feature(self) -> None:
        intent = {"feature": "BGP", "process_id": 1}
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)

        assert plan.changed is False
        assert len(plan.warnings) > 0
        assert "Unsupported feature" in plan.warnings[0]


class SectionUnsupportedSSHConnection:
    """模拟不支持 | section 过滤器的设备 SSH 连接。

    display current-configuration | section 返回 Error，
    其他命令委托给 MockSSHConnection（含 display this 回退路径）。
    """

    def __init__(self, config: SSHConfig) -> None:
        self._inner = MockSSHConnection(config)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def connect(self) -> None:
        self._inner.connect()

    def disconnect(self) -> None:
        self._inner.disconnect()

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        cmd = command.strip()
        if cmd.startswith("display current-configuration") and "| section" in cmd:
            return "Error: Unrecognized command found at '^' position."
        return self._inner.send_command(command, read_timeout)

    def send_config_set(self, config_commands: list[str]) -> str:
        return self._inner.send_config_set(config_commands)

    def send_command_timing(self, command: str) -> str:
        return self._inner.send_command_timing(command)

    def save_config(self) -> str:
        return self._inner.save_config()

    def __enter__(self) -> SectionUnsupportedSSHConnection:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()


class TestVlanConfigReadbackFallback:
    """VLAN 配置回读回退测试：| section 不支持时回退到 display this。"""

    def setup_method(self) -> None:
        config = SSHConfig(host="mock:192.168.1.1", port=22, username="admin", password="test")
        ssh_conn = SectionUnsupportedSSHConnection(config)
        self.driver = HuaweiDevice(
            host="mock:192.168.1.1", port=22, username="admin", password="test",
            ssh_connection=ssh_conn,
        )
        self.driver.connect(ConnectionType.SSH)

    def test_verify_vlan_falls_back_to_display_this(self) -> None:
        """| section 返回 Error 时，通过 display this 成功读取 name/description。"""
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 202,
            "name": "aaa",
            "description": "aaaaa",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        result = self.driver.verify(intent)
        assert result.success is True
        assert result.details.get("actual_name") == "aaa"

    def test_verification_failure_includes_config_raw(self) -> None:
        """验证失败时 details 中包含 config_raw 原始输出，便于诊断。"""
        intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 203,
            "name": "expected_name",
            "description": "expected_desc",
            "device_id": 1,
        }
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        # 用不匹配的期望值触发验证失败
        verify_intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 203,
            "name": "wrong_name",
            "description": "wrong_desc",
            "device_id": 1,
        }
        result = self.driver.verify(verify_intent)
        assert result.success is False
        assert "config_raw" in result.details
        assert "vlan 203" in result.details["config_raw"]
