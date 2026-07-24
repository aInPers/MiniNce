from __future__ import annotations

import re
import time
from typing import Any

from minince.domain.devices.driver import NetworkDeviceDriver
from minince.domain.devices.facts import ConnectionResult, CurrentState, DeviceFacts
from minince.domain.network.config_plan import ConfigPlan, ExecutionResult, VerificationResult
from minince.infrastructure.drivers.huawei_vrp.command_generator import HuaweiVRPCommandGenerator
from minince.infrastructure.drivers.huawei_vrp.parser import HuaweiVRPParser
from minince.infrastructure.ssh.base import SSHConfig, SSHConnection
from minince.shared.enums import RiskLevel


def _create_ssh_connection(config: SSHConfig) -> SSHConnection:
    """根据 host 自动选择 SSH 后端。

    - host 为空或 "mock" 开头时使用 MockSSHConnection（用于测试）
    - 其他情况使用 ParamikoSSHConnection（真实设备）
    """
    if not config.host or config.host.startswith("mock"):
        from minince.infrastructure.ssh.mock_connection import MockSSHConnection
        return MockSSHConnection(config)

    from minince.infrastructure.ssh.paramiko_connection import ParamikoSSHConnection
    return ParamikoSSHConnection(config)


class HuaweiVRPDriver(NetworkDeviceDriver):
    def __init__(
        self,
        host: str = "",
        port: int = 22,
        username: str = "",
        password: str = "",
        enable_password: str = "",
        timeout: int = 30,
        ssh_connection: SSHConnection | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self._ssh_connection = ssh_connection
        self._connected = False
        self._generator = HuaweiVRPCommandGenerator()
        self._parser = HuaweiVRPParser()

        if self._ssh_connection is None:
            ssh_config = SSHConfig(
                host=host or "mock",
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                device_type="",
                enable_password=enable_password,
            )
            self._ssh_connection = _create_ssh_connection(ssh_config)

    def _ensure_connected(self) -> bool:
        """确保 SSH 连接已建立并保持，供实际操作使用。"""
        if self._connected:
            return True
        try:
            self._ssh_connection.connect()
            self._connected = True
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        """断开 SSH 连接，释放设备会话。"""
        if self._connected:
            try:
                self._ssh_connection.disconnect()
            except Exception:
                pass
            self._connected = False

    def test_connection(self) -> ConnectionResult:
        start_time = time.time()
        response_time_ms = 0

        if not self.host:
            return ConnectionResult(
                success=False,
                message="No host configured",
                response_time_ms=0,
                error_type="NO_HOST",
            )

        try:
            self._ssh_connection.connect()
            self._connected = True
            response_time_ms = int((time.time() - start_time) * 1000)
            result = ConnectionResult(
                success=True,
                message=f"Successfully connected to {self.host}:{self.port}",
                response_time_ms=response_time_ms,
            )
        except Exception as e:
            self._connected = False
            result = ConnectionResult(
                success=False,
                message=str(e),
                response_time_ms=response_time_ms,
                error_type="CONNECTION_ERROR",
            )
        finally:
            if self._connected:
                try:
                    self._ssh_connection.disconnect()
                    self._connected = False
                except Exception:
                    pass
        return result

    def get_facts(self) -> DeviceFacts:
        if not self._ensure_connected():
            return DeviceFacts()

        try:
            output = self._ssh_connection.send_command("display version")
            return self._parse_version_output(output)
        except Exception:
            return DeviceFacts()

    def get_current_state(self, intent: object) -> CurrentState:
        if not self._ensure_connected():
            return CurrentState(feature="", exists=False, data={})

        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._get_vlan_state(intent_dict)
        elif feature == "INTERFACE":
            return self._get_interface_state(intent_dict)
        else:
            return CurrentState(feature=feature, exists=False, data={})

    def build_plan(
        self,
        intent: object,
        current_state: CurrentState,
    ) -> ConfigPlan:
        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._generator.generate_vlan_commands(intent_dict, current_state.to_dict())
        elif feature == "INTERFACE":
            return self._generator.generate_interface_commands(intent_dict, current_state.to_dict())
        else:
            return ConfigPlan(
                device_id=int(intent_dict.get("device_id", 0)),
                feature=feature,
                intent=intent_dict,
                current_state=current_state.to_dict(),
                commands=[],
                verify_commands=[],
                changed=False,
                risk_level=RiskLevel.LOW,
                warnings=[f"Unsupported feature: {feature}"],
            )

    def apply_plan(self, plan: ConfigPlan) -> ExecutionResult:
        if not self._ensure_connected():
            return ExecutionResult(
                success=False,
                error_message="Failed to connect to device",
            )

        if not plan.changed:
            return ExecutionResult(
                success=True,
                command_outputs=[{"message": "No changes needed, configuration already matches desired state"}],
            )

        command_outputs: list[dict[str, Any]] = []
        commands_to_execute = [self._generator.SYSTEM_VIEW_ENTER] + plan.commands

        for cmd in commands_to_execute:
            output = self._execute_command(cmd)
            parsed = self._parser.parse_command_output(output)
            command_outputs.append({
                "command": cmd,
                "output": output,
                "success": parsed["success"],
            })
            if not parsed["success"]:
                return ExecutionResult(
                    success=False,
                    command_outputs=command_outputs,
                    error_message=f"Command failed: {cmd}",
                )

        self._save_config()

        return ExecutionResult(
            success=True,
            command_outputs=command_outputs,
        )

    def verify(self, intent: object) -> VerificationResult:
        if not self._ensure_connected():
            return VerificationResult(
                success=False,
                error_message="Failed to connect to device for verification",
            )

        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._verify_vlan(intent_dict)
        elif feature == "INTERFACE":
            return self._verify_interface(intent_dict)
        else:
            return VerificationResult(
                success=False,
                error_message=f"Unsupported feature for verification: {feature}",
            )

    def get_running_config(self) -> str:
        if not self._ensure_connected():
            return ""

        try:
            output = self._ssh_connection.send_command("display current-configuration")
            return output
        except Exception:
            return ""

    def backup_config(self, backup_path: str) -> bool:
        config = self.get_running_config()
        if not config:
            return False

        from pathlib import Path
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
        Path(backup_path).write_text(config, encoding="utf-8")
        return True

    def _get_vlan_state(self, intent_dict: dict[str, Any]) -> CurrentState:
        """从真实设备获取 VLAN 状态。

        使用 display vlan {id} 判断 VLAN 是否存在，
        使用 display current-configuration | section vlan {id} 获取 name 和 description，
        并检测是否存在关联的 VLANIF 接口（删除时需先删除）。
        """
        vlan_id = intent_dict.get("vlan_id", 0)

        # 1. 判断 VLAN 是否存在
        try:
            output = self._ssh_connection.send_command(f"display vlan {vlan_id}")
        except Exception as e:
            return CurrentState(
                feature="VLAN",
                exists=False,
                data={"error": f"Failed to query VLAN: {e}"},
            )

        if not output or "does not exist" in output.lower() or "Error" in output:
            return CurrentState(feature="VLAN", exists=False, data={})

        # 2. 获取 VLAN 详细配置（name, description）
        name = ""
        description = ""
        try:
            config_output = self._ssh_connection.send_command(
                f"display current-configuration | section vlan {vlan_id}"
            )
            if config_output and "Error" not in config_output:
                name, description = self._parse_vlan_config_section(config_output, vlan_id)
        except Exception:
            pass

        # 3. 检测是否存在关联的 VLANIF 接口（L3 接口）
        has_vlanif = self._check_vlanif_exists(vlan_id)

        return CurrentState(
            feature="VLAN",
            exists=True,
            data={
                "vlan_id": vlan_id,
                "name": name,
                "description": description,
                "has_vlanif": has_vlanif,
            },
        )

    def _check_vlanif_exists(self, vlan_id: int) -> bool:
        """检测指定 VLAN 是否关联了 VLANIF 接口（Layer 3 虚拟接口）。

        使用 display current-configuration interface Vlanif{id} 查询，
        若输出中包含 "interface Vlanif{id}" 则认为存在。

        Args:
            vlan_id: VLAN 编号

        Returns:
            True 表示存在 VLANIF 接口，False 表示不存在
        """
        try:
            output = self._ssh_connection.send_command(
                f"display current-configuration interface Vlanif{vlan_id}"
            )
        except Exception:
            return False

        if not output:
            return False

        # 真实设备在接口不存在时会返回错误信息
        if "Error" in output or "does not exist" in output.lower():
            return False

        # 检查输出中是否包含 Vlanif 接口定义
        return f"interface Vlanif{vlan_id}" in output

    def _get_interface_state(self, intent_dict: dict[str, Any]) -> CurrentState:
        """从真实设备获取接口状态。

        使用 display current-configuration interface {ifname} 获取接口配置。
        """
        ifname = intent_dict.get("interface_name", "")
        if not ifname:
            return CurrentState(feature="INTERFACE", exists=False, data={})

        try:
            output = self._ssh_connection.send_command(
                f"display current-configuration interface {ifname}"
            )
        except Exception as e:
            return CurrentState(
                feature="INTERFACE",
                exists=False,
                data={"error": f"Failed to query interface: {e}"},
            )

        if not output or "Error" in output or "does not exist" in output.lower():
            return CurrentState(feature="INTERFACE", exists=False, data={})

        return self._parse_interface_config(output, ifname)

    def _execute_command(self, command: str) -> str:
        cmd = command.strip()
        return self._ssh_connection.send_command(cmd)

    def _save_config(self) -> None:
        try:
            self._ssh_connection.save_config()
        except Exception:
            pass

    def _to_dict(self, intent: object) -> dict[str, Any]:
        if isinstance(intent, dict):
            return intent
        if hasattr(intent, "model_dump"):
            return intent.model_dump()
        if hasattr(intent, "dict"):
            return intent.dict()
        return {"feature": str(intent)}

    def _parse_version_output(self, output: str) -> DeviceFacts:
        hostname_match = re.search(r"(\S+)\s+uptime", output)
        hostname = hostname_match.group(1) if hostname_match else self.host or "UNKNOWN"

        model_match = re.search(r"Huawei\s+(\S+)\s+Router", output, re.IGNORECASE)
        if not model_match:
            model_match = re.search(r"(\w+-\w+-\w+-\w+)", output)
        model = model_match.group(1) if model_match else "Unknown"

        version_match = re.search(r"Software,\s*Version\s+(.+)", output)
        firmware = version_match.group(1).strip() if version_match else "Unknown"

        uptime_match = re.search(r"uptime is (.+)", output)
        uptime = uptime_match.group(1).strip() if uptime_match else "0 days, 0:00:00"

        return DeviceFacts(
            hostname=hostname,
            model=model,
            firmware_version=firmware,
            vendor="HUAWEI",
            serial_number="",
            uptime=uptime,
        )

    @staticmethod
    def _parse_vlan_list(vlan_str: str) -> list[int]:
        """从字符串中解析 VLAN 列表，支持空格、逗号分隔及范围表示。

        支持格式：
        - "10 20 30"（空格分隔）
        - "10,20,30"（逗号分隔）
        - "10-20"（范围）
        - "10 20-30,40"（混合）

        Args:
            vlan_str: 包含 VLAN 编号的字符串

        Returns:
            解析后的 VLAN 编号列表
        """
        vlans: list[int] = []
        # 将逗号统一替换为空格后再按空格切分，统一处理两种分隔符
        normalized = vlan_str.replace(",", " ")
        for part in normalized.split():
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_end = part.split("-", 1)
                try:
                    start, end = int(start_end[0]), int(start_end[1])
                    vlans.extend(range(start, end + 1))
                except (ValueError, IndexError):
                    pass
            elif part.isdigit():
                vlans.append(int(part))
        return vlans

    def _parse_vlan_config_section(self, output: str, vlan_id: int) -> tuple[str, str]:
        """从 display current-configuration | section vlan {id} 输出中解析 name 和 description。

        华为 VRP 输出格式：
        #
        vlan 100
         name TEST_NAME
         description TEST_DESC
        #
        """
        name = ""
        description = ""

        name_match = re.search(r"^\s*name\s+(\S+)", output, re.MULTILINE)
        if name_match:
            name = name_match.group(1)

        desc_match = re.search(r"^\s*description\s+(.+)", output, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()

        return name, description

    def _parse_interface_config(self, output: str, ifname: str) -> CurrentState:
        """从 display current-configuration interface {ifname} 输出中解析接口配置。

        华为 VRP 输出格式：
        #
        interface GigabitEthernet0/0/0
         description TEST_DESC
         port link-type access
         port default vlan 10
         undo shutdown
        #
        """
        description = ""
        link_type = ""
        access_vlan: int | None = None
        trunk_vlans: list[int] = []
        admin_up = True

        desc_match = re.search(r"^\s*description\s+(.+)", output, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()

        link_match = re.search(r"port link-type\s+(\w+)", output)
        if link_match:
            link_type = link_match.group(1)

        access_match = re.search(r"port default vlan\s+(\d+)", output)
        if access_match:
            access_vlan = int(access_match.group(1))

        trunk_match = re.search(r"port trunk allow-pass vlan\s+(.+)", output)
        if trunk_match:
            vlan_str = trunk_match.group(1).strip()
            trunk_vlans.extend(self._parse_vlan_list(vlan_str))

        if "shutdown" in output and "undo shutdown" not in output:
            admin_up = False

        return CurrentState(
            feature="INTERFACE",
            exists=True,
            data={
                "interface_name": ifname,
                "description": description,
                "admin_up": admin_up,
                "link_type": link_type,
                "access_vlan": access_vlan,
                "trunk_allowed_vlans": trunk_vlans,
            },
        )

    def _verify_vlan(self, intent_dict: dict[str, Any]) -> VerificationResult:
        vlan_id = intent_dict.get("vlan_id", 0)
        expected_name = intent_dict.get("name")
        expected_desc = intent_dict.get("description")
        operation = intent_dict.get("operation", "create")

        try:
            output = self._ssh_connection.send_command(f"display vlan {vlan_id}")
        except Exception as e:
            return VerificationResult(
                success=False,
                error_message=f"Failed to verify VLAN {vlan_id}: {e}",
                details={"vlan_id": vlan_id},
            )

        return self._verify_vlan_from_output(output, vlan_id, expected_name, expected_desc, operation)

    def _verify_vlan_from_output(
        self,
        output: str,
        vlan_id: int,
        expected_name: str | None,
        expected_desc: str | None,
        operation: str,
    ) -> VerificationResult:
        if operation == "delete":
            if "does not exist" in output.lower() or "Error" in output:
                return VerificationResult(
                    success=True,
                    verification_outputs=[{"message": f"VLAN {vlan_id} successfully deleted"}],
                    details={"vlan_id": vlan_id, "status": "deleted"},
                )
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} still exists after delete operation",
                details={"vlan_id": vlan_id, "output": output[:200]},
            )

        if "does not exist" in output.lower() or "Error" in output:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} not found after configuration",
                details={"vlan_id": vlan_id},
            )

        # VLAN 存在，获取详细配置进行验证
        actual_name = ""
        actual_desc = ""
        try:
            config_output = self._ssh_connection.send_command(
                f"display current-configuration | section vlan {vlan_id}"
            )
            if config_output and "Error" not in config_output:
                actual_name, actual_desc = self._parse_vlan_config_section(config_output, vlan_id)
        except Exception:
            pass

        mismatches: list[str] = []
        if expected_name and actual_name != expected_name:
            mismatches.append(f"name mismatch: expected '{expected_name}', got '{actual_name}'")
        if expected_desc and actual_desc != expected_desc:
            mismatches.append(f"description mismatch: expected '{expected_desc}', got '{actual_desc}'")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} verification failed: {'; '.join(mismatches)}",
                details={"vlan_id": vlan_id, "mismatches": mismatches},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"VLAN {vlan_id} verification passed"}],
            details={"vlan_id": vlan_id, "actual_name": actual_name, "actual_desc": actual_desc},
        )

    def _verify_interface(self, intent_dict: dict[str, Any]) -> VerificationResult:
        ifname = intent_dict.get("interface_name", "")
        expected_desc = intent_dict.get("description")
        expected_admin_up = intent_dict.get("admin_up")
        expected_link_type = intent_dict.get("link_type")
        expected_access_vlan = intent_dict.get("access_vlan")
        expected_trunk_vlans = intent_dict.get("trunk_allowed_vlans")

        try:
            output = self._ssh_connection.send_command(
                f"display current-configuration interface {ifname}"
            )
        except Exception as e:
            return VerificationResult(
                success=False,
                error_message=f"Failed to verify interface {ifname}: {e}",
                details={"interface_name": ifname},
            )

        return self._verify_interface_from_output(
            output, ifname, expected_desc, expected_admin_up,
            expected_link_type, expected_access_vlan, expected_trunk_vlans,
        )

    def _verify_interface_from_output(
        self,
        output: str,
        ifname: str,
        expected_desc: str | None,
        expected_admin_up: bool | None,
        expected_link_type: str | None,
        expected_access_vlan: int | None,
        expected_trunk_vlans: list[int] | None,
    ) -> VerificationResult:
        if "Error" in output or "does not exist" in output.lower():
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} not found after configuration",
                details={"interface_name": ifname},
            )

        mismatches: list[str] = []

        desc_match = re.search(r"^\s*description\s+(.+)", output, re.MULTILINE)
        if expected_desc is not None and desc_match:
            actual_desc = desc_match.group(1).strip()
            if actual_desc != expected_desc:
                mismatches.append(f"description mismatch: expected '{expected_desc}', got '{actual_desc}'")

        if "shutdown" in output and "undo shutdown" not in output:
            actual_up = False
        else:
            actual_up = True
        if expected_admin_up is not None and actual_up != expected_admin_up:
            mismatches.append(f"admin state mismatch: expected {'up' if expected_admin_up else 'down'}, got {'up' if actual_up else 'down'}")

        link_type_match = re.search(r"port link-type\s+(\w+)", output)
        if expected_link_type is not None and link_type_match:
            actual_type = link_type_match.group(1)
            if actual_type != expected_link_type:
                mismatches.append(f"link type mismatch: expected {expected_link_type}, got {actual_type}")

        access_match = re.search(r"port default vlan\s+(\d+)", output)
        if expected_access_vlan is not None and access_match:
            actual_vlan = int(access_match.group(1))
            if actual_vlan != expected_access_vlan:
                mismatches.append(f"access VLAN mismatch: expected {expected_access_vlan}, got {actual_vlan}")

        if expected_trunk_vlans is not None:
            trunk_match = re.search(r"port trunk allow-pass vlan\s+(.+)", output)
            if trunk_match:
                vlan_str = trunk_match.group(1).strip()
                actual_vlans = self._parse_vlan_list(vlan_str)
                expected_set = set(expected_trunk_vlans)
                actual_set = set(actual_vlans)
                if actual_set != expected_set:
                    mismatches.append(f"trunk VLAN mismatch: expected {sorted(expected_set)}, got {sorted(actual_set)}")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} verification failed: {'; '.join(mismatches)}",
                details={"interface_name": ifname, "mismatches": mismatches},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"Interface {ifname} verification passed"}],
            details={"interface_name": ifname},
        )
