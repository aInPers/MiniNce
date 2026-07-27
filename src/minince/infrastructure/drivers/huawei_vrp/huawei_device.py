from __future__ import annotations

import re
import time
from typing import Any

from minince.domain.devices.config import DeviceConfig
from minince.domain.devices.facts import ConnectionResult, CurrentState, DeviceFacts
from minince.domain.devices.network_device import NetworkDevice
from minince.domain.network.config_plan import (
    ConfigPlan,
    ExecutionResult,
    VerificationResult,
)
from minince.infrastructure.drivers.huawei_vrp.command_generator import (
    HuaweiVRPCommandGenerator,
)
from minince.infrastructure.drivers.huawei_vrp.ospf_parser import HuaweiOspfParser
from minince.infrastructure.drivers.huawei_vrp.ospf_renderer import HuaweiOspfRenderer
from minince.infrastructure.drivers.huawei_vrp.parser import HuaweiVRPParser
from minince.infrastructure.ssh.base import SSHConfig, SSHConnection
from minince.shared.enums import ConnectionType, DeviceType


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


class HuaweiDevice(NetworkDevice):
    """华为 VRP 设备实现类。

    通过 SSH 连接华为 VRP（Versatile Routing Platform）设备，
    实现网络设备接口类定义的全部 12 个方法。
    """

    # VRP 视图导航命令，回滚时无需 undo
    _NAV_COMMANDS = frozenset({
        "system-view", "sys", "quit", "return", "save", "save force",
        "display this",
    })

    # 多关键字命令：undo 仅保留关键字前缀（去掉参数值）
    _KEYWORD_UNDO_PREFIXES: list[str] = [
        "port link-type",
        "port default vlan",
        "ip address",
        "description",
        "sysname",
        "ospf cost",
        "ospf network-type",
        "ospf authentication-mode",
        "ospf enable",
        "silent-interface",
        "router-id",
    ]

    # 需要完整 undo 的命令前缀（undo + 完整原命令）
    _FULL_UNDO_PREFIXES: list[str] = [
        "port trunk allow-pass vlan",
        "vlan",
        "ospf",
        "network",
        "area",
    ]

    def __init__(
        self,
        host: str = "",
        port: int = 22,
        username: str = "",
        password: str = "",
        enable_password: str = "",
        timeout: int = 30,
        ssh_connection: SSHConnection | None = None,
        auto_add_host_key: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self._ssh_connection = ssh_connection
        self._connected = False

        if self._ssh_connection is None:
            ssh_config = SSHConfig(
                host=host or "mock",
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                device_type="",
                enable_password=enable_password,
                auto_add_host_key=auto_add_host_key,
            )
            self._ssh_connection = _create_ssh_connection(ssh_config)

    # ------------------------------------------------------------------
    # 设备信息
    # ------------------------------------------------------------------
    def get_type(self) -> DeviceType:
        """通过解析 display version 确定设备类型。"""
        output = self._query("display version")
        if not output:
            return DeviceType.ROUTER

        output_lower = output.lower()
        if "switch" in output_lower:
            return DeviceType.SWITCH
        if "router" in output_lower:
            return DeviceType.ROUTER

        # 回退：按型号前缀判断
        model = self._extract_model(output)
        if model.upper().startswith("S"):
            return DeviceType.SWITCH
        return DeviceType.ROUTER

    def get_vendor(self) -> str:
        """返回设备厂家。"""
        return "HUAWEI"

    def get_model(self) -> str:
        """通过解析 display version 获取设备型号。"""
        output = self._query("display version")
        return self._extract_model(output)

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------
    def get_all_configs(self) -> DeviceConfig:
        """获取设备所有配置信息，以配置段为键值返回。"""
        output = self._query("display current-configuration")
        if not output:
            return DeviceConfig()

        sections = self._parse_config_sections(output)
        return DeviceConfig(sections)

    def get_config(self, name: str) -> DeviceConfig:
        """获取对应名称的配置段。"""
        all_configs = self.get_all_configs()
        # 精确匹配优先
        if all_configs.has(name):
            return DeviceConfig({name: all_configs.get(name)})

        # 模糊匹配：键包含指定名称
        for key in all_configs.keys():
            if name.lower() in key.lower():
                return DeviceConfig({key: all_configs.get(key)})

        return DeviceConfig()

    def push_config(self, config: DeviceConfig) -> bool:
        """下发配置，途中失败则 undo 逆序回滚已执行成功的命令。"""
        if not self._ensure_connected():
            return False

        commands: list[str] = config.get("commands", [])
        if not isinstance(commands, list):
            return False

        # 在系统视图下逐条执行
        executed: list[str] = []
        self._send("system-view")
        try:
            for cmd in commands:
                output = self._send(cmd)
                if self._is_error(output):
                    # 失败：逆序 undo 已执行成功的命令
                    self._rollback(executed)
                    self._send("return")
                    return False
                executed.append(cmd)
        finally:
            pass

        self._send("return")
        self._save_config()
        return True

    # ------------------------------------------------------------------
    # 邻居发现
    # ------------------------------------------------------------------
    def get_neighbors(self) -> list[tuple[str, str]]:
        """通过 LLDP 查看周边网络设备，返回 (设备名, IP) 二元组列表。"""
        output = self._query("display lldp neighbor brief")
        if not output:
            return []

        return self._parse_lldp_neighbors(output)

    # ------------------------------------------------------------------
    # 接口配置
    # ------------------------------------------------------------------
    def get_interface_config(self, interface_name: str) -> DeviceConfig:
        """获取对应接口配置，以结构化键值返回。"""
        output = self._query(
            f"display current-configuration interface {interface_name}"
        )
        if not output or "Error" in output:
            return DeviceConfig()

        return self._parse_interface_config(output, interface_name)

    def set_interface_config(
        self, interface_name: str, config: DeviceConfig
    ) -> bool:
        """设置接口配置，途中失败则 undo 逆序回滚。"""
        if not self._ensure_connected():
            return False

        # 生成 (命令, undo命令) 对
        command_pairs = self._render_interface_commands(config)
        if not command_pairs:
            return True

        executed_undos: list[str] = []

        self._send("system-view")
        self._send(f"interface {interface_name}")

        try:
            for cmd, undo_cmd in command_pairs:
                output = self._send(cmd)
                if self._is_error(output):
                    # 失败：逆序执行已记录的 undo 命令
                    self._rollback_undos(executed_undos)
                    self._send("return")
                    return False
                if undo_cmd is not None:
                    executed_undos.append(undo_cmd)
        finally:
            pass

        self._send("return")
        self._save_config()
        return True

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def connect(self, connection_type: ConnectionType) -> ConnectionResult:
        """按照连接类型开始连接并返回连接信息。"""
        if connection_type != ConnectionType.SSH:
            return ConnectionResult(
                success=False,
                message=f"暂不支持的连接类型: {connection_type}",
                error_type="UNSUPPORTED_CONNECTION_TYPE",
            )

        start_time = time.time()
        if not self.host:
            return ConnectionResult(
                success=False,
                message="未配置设备主机地址",
                error_type="NO_HOST",
            )

        try:
            self._ssh_connection.connect()
            self._connected = True
            response_time_ms = int((time.time() - start_time) * 1000)
            return ConnectionResult(
                success=True,
                message=f"成功连接到 {self.host}:{self.port}",
                response_time_ms=response_time_ms,
            )
        except Exception as e:
            self._connected = False
            return ConnectionResult(
                success=False,
                message=str(e),
                error_type="CONNECTION_ERROR",
            )

    def set_credentials(self, username: str, password: str) -> None:
        """设置用户名与密码，供后续连接使用。"""
        self.username = username
        self.password = password

    def close(self) -> bool:
        """关闭连接，返回关闭结果。"""
        if not self._connected:
            return True
        try:
            self._ssh_connection.disconnect()
            self._connected = False
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        """关闭连接（与 close() 等价，提供统一接口名）。"""
        self.close()

    # ------------------------------------------------------------------
    # 设备信息扩展
    # ------------------------------------------------------------------
    def get_facts(self) -> DeviceFacts:
        """获取设备基本信息（厂商、型号、主机名、版本等）。"""
        vendor = self.get_vendor()

        version_output = self._query("display version")
        model = self._extract_model(version_output) if version_output else "Unknown"

        firmware_version = ""
        if version_output:
            version_match = re.search(
                r"VRP.*?Version\s+([\w\s\(\)]+?)(?:\n|$)", version_output
            )
            if version_match:
                firmware_version = version_match.group(1).strip()

        hostname = ""
        config_output = self._query("display current-configuration")
        if config_output:
            sysname_match = re.search(
                r"^sysname\s+(\S+)", config_output, re.MULTILINE
            )
            if sysname_match:
                hostname = sysname_match.group(1)

        return DeviceFacts(
            hostname=hostname,
            model=model,
            firmware_version=firmware_version,
            vendor=vendor,
        )

    # ------------------------------------------------------------------
    # 模板配置：状态获取、计划构建、执行、验证
    # ------------------------------------------------------------------
    def get_current_state(self, intent: dict[str, Any]) -> CurrentState:
        """获取指定特性的当前设备状态。"""
        feature = intent.get("feature", "").upper()

        if feature == "VLAN":
            return self._get_vlan_state(intent)
        if feature == "INTERFACE":
            return self._get_interface_state(intent)
        if feature == "OSPF":
            return self._get_ospf_state(intent)
        return CurrentState(feature=feature, exists=False, data={})

    def build_plan(
        self,
        intent: dict[str, Any],
        current_state: CurrentState,
    ) -> ConfigPlan:
        """构建配置计划。"""
        feature = intent.get("feature", "").upper()

        if feature == "VLAN":
            generator = HuaweiVRPCommandGenerator()
            return generator.generate_vlan_commands(intent, current_state.to_dict())
        if feature == "INTERFACE":
            generator = HuaweiVRPCommandGenerator()
            return generator.generate_interface_commands(
                intent, current_state.to_dict()
            )
        if feature == "OSPF":
            renderer = HuaweiOspfRenderer()
            return renderer.generate_commands(intent, current_state.data)
        return ConfigPlan(
            device_id=int(intent.get("device_id", 0)),
            feature=feature,
            intent=intent,
            current_state={},
            commands=[],
            changed=False,
            warnings=[f"Unsupported feature: {feature}"],
        )

    def apply_plan(self, plan: ConfigPlan) -> ExecutionResult:
        """在设备上执行配置计划。"""
        if not self._ensure_connected():
            return ExecutionResult(success=False, error_message="SSH connection failed")

        if not plan.commands:
            return ExecutionResult(success=True, command_outputs=[])

        command_outputs: list[dict[str, Any]] = []

        self._send("system-view")
        try:
            for cmd in plan.commands:
                output = self._send(cmd)
                command_outputs.append({"command": cmd, "output": output})
                if self._is_error(output):
                    return ExecutionResult(
                        success=False,
                        command_outputs=command_outputs,
                        error_message=f"Command failed: {cmd.strip()}",
                    )
        finally:
            self._send("return")

        self._save_config()
        return ExecutionResult(success=True, command_outputs=command_outputs)

    def verify(self, intent: dict[str, Any]) -> VerificationResult:
        """验证配置是否生效。"""
        feature = intent.get("feature", "").upper()

        if feature == "VLAN":
            return self._verify_vlan(intent)
        if feature == "INTERFACE":
            return self._verify_interface(intent)
        if feature == "OSPF":
            return self._verify_ospf(intent)
        return VerificationResult(
            success=False,
            error_message=f"Unsupported feature: {feature}",
        )

    # ------------------------------------------------------------------
    # 内部辅助：状态获取
    # ------------------------------------------------------------------
    def _get_vlan_state(self, intent: dict[str, Any]) -> CurrentState:
        """获取 VLAN 当前状态。"""
        vlan_id = intent.get("vlan_id", 0)
        output = self._query(f"display vlan {vlan_id}")

        if not output or "Error" in output:
            return CurrentState(feature="VLAN", exists=False, data={})

        # 解析 name 和 description（兼容 mock 与真实设备输出）
        name: str | None = None
        name_match = re.search(r"(?:VLAN\s+)?Name\s*:\s*(\S+)", output, re.IGNORECASE)
        if name_match:
            name = name_match.group(1)
        if not name:
            name_match = re.search(r"^\s*name\s+(\S+)", output, re.MULTILINE)
            if name_match:
                name = name_match.group(1)

        desc: str | None = None
        desc_match = re.search(r"Description\s*:\s*(.+)", output, re.IGNORECASE)
        if desc_match:
            desc = desc_match.group(1).strip()

        # 检测是否关联 Vlanif 三层接口
        has_vlanif = False
        vlanif_output = self._query(
            f"display current-configuration interface Vlanif{vlan_id}"
        )
        if (
            vlanif_output
            and "Error" not in vlanif_output
            and f"interface Vlanif{vlan_id}" in vlanif_output
        ):
            has_vlanif = True

        return CurrentState(
            feature="VLAN",
            exists=True,
            data={
                "vlan_id": vlan_id,
                "name": name,
                "description": desc,
                "has_vlanif": has_vlanif,
            },
        )

    def _get_interface_state(self, intent: dict[str, Any]) -> CurrentState:
        """获取接口当前状态。"""
        ifname = intent.get("interface_name", "")
        output = self._query(f"display current-configuration interface {ifname}")

        if not output or "Error" in output:
            return CurrentState(feature="INTERFACE", exists=False, data={})

        config = self._parse_interface_config(output, ifname)
        return CurrentState(
            feature="INTERFACE",
            exists=True,
            data=config.to_dict(),
        )

    def _get_ospf_state(self, intent: dict[str, Any]) -> CurrentState:
        """获取 OSPF 进程当前状态。"""
        process_id = intent.get("process_id", 1)
        config_output = self._query("display current-configuration configuration ospf")

        parser = HuaweiOspfParser()
        state = parser.parse_running_config(config_output or "", process_id)

        return CurrentState(
            feature="OSPF",
            exists=state.running,
            data=state.to_dict(),
        )

    # ------------------------------------------------------------------
    # 内部辅助：验证
    # ------------------------------------------------------------------
    def _verify_vlan(self, intent: dict[str, Any]) -> VerificationResult:
        """验证 VLAN 配置。"""
        vlan_id = intent.get("vlan_id", 0)
        operation = intent.get("operation", "create")

        display_output = self._query(f"display vlan {vlan_id}")
        vlan_exists = (
            bool(display_output)
            and "Error" not in display_output
            and str(vlan_id) in display_output
        )

        if operation == "delete":
            if not vlan_exists:
                return VerificationResult(
                    success=True,
                    details={"status": "deleted", "vlan_id": vlan_id},
                )
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} still exists after deletion",
                details={"status": "exists", "vlan_id": vlan_id},
            )

        if not vlan_exists:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} does not exist",
                details={"status": "not_found", "vlan_id": vlan_id},
            )

        # 尝试 | section 获取详细配置，失败时回退到 display this
        config_raw = self._query(
            f"display current-configuration | section vlan {vlan_id}"
        )
        if not config_raw or "Error" in config_raw:
            self._send("system-view")
            self._send(f"vlan {vlan_id}")
            config_raw = self._send("display this")
            self._send("quit")
            self._send("return")

        # 从配置段中解析特定 VLAN 的 name 和 description
        actual_name = ""
        actual_desc = ""
        vlan_section = re.search(
            rf"vlan\s+{vlan_id}\b(.*?)(?=\n\s*vlan\s+\d|\n#|\ninterface\s|\nreturn|\Z)",
            config_raw,
            re.DOTALL,
        )
        section_text = vlan_section.group(1) if vlan_section else config_raw

        name_match = re.search(r"^\s*name\s+(\S+)", section_text, re.MULTILINE)
        if name_match:
            actual_name = name_match.group(1)
        desc_match = re.search(r"^\s*description\s+(.+)", section_text, re.MULTILINE)
        if desc_match:
            actual_desc = desc_match.group(1).strip()

        success = True
        expected_name = intent.get("name")
        expected_desc = intent.get("description")
        if expected_name and expected_name != actual_name:
            success = False
        if expected_desc and expected_desc != actual_desc:
            success = False

        return VerificationResult(
            success=success,
            details={
                "vlan_id": vlan_id,
                "actual_name": actual_name,
                "actual_description": actual_desc,
                "config_raw": config_raw,
            },
        )

    def _verify_interface(self, intent: dict[str, Any]) -> VerificationResult:
        """验证接口配置。"""
        ifname = intent.get("interface_name", "")
        output = self._query(f"display current-configuration interface {ifname}")

        if not output or "Error" in output:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} not found",
            )

        config = self._parse_interface_config(output, ifname)

        success = True
        if intent.get("description") is not None and intent["description"] != config.get("description"):
            success = False
        if intent.get("admin_up") is not None and intent["admin_up"] != config.get("admin_up"):
            success = False
        if intent.get("link_type") and intent["link_type"] != config.get("link_type"):
            success = False
        if intent.get("access_vlan") is not None and intent["access_vlan"] != config.get("access_vlan"):
            success = False

        return VerificationResult(
            success=success,
            details={"interface_name": ifname, "config": config.to_dict()},
        )

    def _verify_ospf(self, intent: dict[str, Any]) -> VerificationResult:
        """验证 OSPF 配置。"""
        process_id = intent.get("process_id", 1)
        operation = intent.get("operation", "ensure_present")

        parser = HuaweiOspfParser()

        brief_output = self._query(f"display ospf brief process {process_id}")
        running, _ = parser.parse_brief(brief_output, process_id)

        if operation == "ensure_absent":
            if not running:
                return VerificationResult(
                    success=True,
                    details={"status": "deleted", "process_id": process_id},
                )
            return VerificationResult(
                success=False,
                error_message=f"OSPF process {process_id} still running",
                details={"status": "running", "process_id": process_id},
            )

        if not running:
            return VerificationResult(
                success=False,
                error_message=f"OSPF process {process_id} not running",
                details={"process_running": False},
            )

        # 验证接口
        iface_output = self._query(f"display ospf interface process {process_id}")
        iface_states = parser.parse_interface_display(iface_output)
        iface_names = {
            i.get("interface_name", "").lower() for i in iface_states
        }

        interfaces_valid = True
        intent_ifaces = intent.get("interfaces") or []
        for iface_intent in intent_ifaces:
            name = iface_intent.get("interface_name", "")
            if name.lower() not in iface_names:
                interfaces_valid = False
                break

        # 验证邻居
        neighbors_full: bool | None = None
        neighbors_expected: bool | None = None
        expected_neighbors = intent.get("expected_neighbors")
        if expected_neighbors:
            peer_output = self._query(f"display ospf peer process {process_id}")
            peers = parser.parse_peer(peer_output)
            full_peers = {p["neighbor_id"] for p in peers if p["is_full"]}
            expected_set = set(expected_neighbors)
            neighbors_full = expected_set.issubset(full_peers)
            neighbors_expected = neighbors_full

        success = running and interfaces_valid
        if expected_neighbors:
            success = success and bool(neighbors_expected)

        return VerificationResult(
            success=success,
            details={
                "process_running": running,
                "interfaces_valid": interfaces_valid,
                "neighbors_full": neighbors_full,
                "neighbors_expected": neighbors_expected,
            },
        )

    # ------------------------------------------------------------------
    # 内部辅助：连接与命令执行
    # ------------------------------------------------------------------
    def _ensure_connected(self) -> bool:
        """确保 SSH 连接已建立。"""
        if self._connected:
            return True
        try:
            self._ssh_connection.connect()
            self._connected = True
            return True
        except Exception:
            return False

    def _send(self, command: str) -> str:
        """发送单条命令并返回输出。"""
        return self._ssh_connection.send_command(command.strip())

    def _query(self, command: str) -> str:
        """发送查询命令，连接失败时返回空字符串。"""
        if not self._ensure_connected():
            return ""
        try:
            return self._ssh_connection.send_command(command)
        except Exception:
            return ""

    def _save_config(self) -> None:
        """保存配置到设备。"""
        try:
            self._ssh_connection.save_config()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 内部辅助：回滚
    # ------------------------------------------------------------------
    def _rollback(self, executed_commands: list[str]) -> None:
        """对已执行的命令生成 undo 并逆序执行。"""
        for cmd in reversed(executed_commands):
            undo_cmd = self._generate_undo_command(cmd)
            if undo_cmd is not None:
                try:
                    self._send(undo_cmd)
                except Exception:
                    pass

    def _rollback_undos(self, undo_commands: list[str]) -> None:
        """逆序执行预生成的 undo 命令。"""
        for undo_cmd in reversed(undo_commands):
            try:
                self._send(undo_cmd)
            except Exception:
                pass

    def _generate_undo_command(self, command: str) -> str | None:
        """为 VRP 配置命令生成对应的 undo 命令。

        Returns:
            undo 命令字符串，或 None（无需 undo 的导航/视图命令）
        """
        cmd = command.strip()
        if not cmd:
            return None

        # 导航/视图命令：无需 undo
        if cmd in self._NAV_COMMANDS:
            return None
        if cmd.startswith("interface "):
            return None

        # undo X -> X（反向恢复）
        if cmd.startswith("undo "):
            return cmd[5:]

        # 需要完整 undo 的命令（undo + 原命令全文）
        for prefix in self._FULL_UNDO_PREFIXES:
            if cmd == prefix or cmd.startswith(prefix + " "):
                return f"undo {cmd}"

        # 多关键字命令：undo 仅保留关键字前缀
        for prefix in self._KEYWORD_UNDO_PREFIXES:
            if cmd.startswith(prefix):
                return f"undo {prefix}"

        # 默认：undo + 首个关键字
        first_token = cmd.split()[0]
        return f"undo {first_token}"

    # ------------------------------------------------------------------
    # 内部辅助：命令渲染
    # ------------------------------------------------------------------
    def _render_interface_commands(
        self, config: DeviceConfig
    ) -> list[tuple[str, str | None]]:
        """将接口配置键值渲染为 (命令, undo命令) 列表。"""
        pairs: list[tuple[str, str | None]] = []

        desc = config.get("description")
        if desc is not None:
            pairs.append((f"description {desc}", "undo description"))

        admin_up = config.get("admin_up")
        if admin_up is not None:
            if admin_up:
                pairs.append(("undo shutdown", "shutdown"))
            else:
                pairs.append(("shutdown", "undo shutdown"))

        link_type = config.get("link_type")
        if link_type:
            pairs.append((f"port link-type {link_type}", "undo port link-type"))

        access_vlan = config.get("access_vlan")
        if access_vlan:
            pairs.append(
                (f"port default vlan {access_vlan}", "undo port default vlan")
            )

        trunk_vlans = config.get("trunk_allowed_vlans")
        if trunk_vlans and isinstance(trunk_vlans, list):
            vlan_str = " ".join(str(v) for v in trunk_vlans)
            pairs.append(
                (
                    f"port trunk allow-pass vlan {vlan_str}",
                    f"undo port trunk allow-pass vlan {vlan_str}",
                )
            )

        return pairs

    # ------------------------------------------------------------------
    # 内部辅助：输出解析
    # ------------------------------------------------------------------
    @staticmethod
    def _is_error(output: str) -> bool:
        """判断 VRP 输出是否为错误信息。"""
        if not output:
            return False
        lower = output.lower()
        return "error" in lower or "unrecognized command" in lower

    @staticmethod
    def _extract_model(output: str) -> str:
        """从 display version 输出中解析设备型号。"""
        # 匹配 "HUAWEI S5720-28X-SI-AC uptime" 或 "Huawei S5720 Router"
        model_match = re.search(
            r"(?:Huawei|HUAWEI)\s+(\S+)\s+(?:uptime|Router|Switch)",
            output,
            re.IGNORECASE,
        )
        if model_match:
            return model_match.group(1)

        # 回退：匹配带连字符的型号模式
        model_match = re.search(r"(\w+-\w+-\w+-\w+)", output)
        if model_match:
            return model_match.group(1)

        return "Unknown"

    @staticmethod
    def _parse_config_sections(output: str) -> dict[str, str]:
        """将 display current-configuration 输出按 '#' 分隔符解析为配置段字典。

        Returns:
            键为每段首行（如 "sysname SW-MOCK"、"interface GE0/0/0"），
            值为该段剩余配置行文本。
        """
        sections: dict[str, str] = {}
        # 按空行或 '#' 分隔为段
        raw_sections = re.split(r"^#", output, flags=re.MULTILINE)

        for raw in raw_sections:
            lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
            if not lines:
                continue
            # 跳过版本信息行
            if lines[0].startswith("!"):
                lines = lines[1:]
                if not lines:
                    continue
            key = lines[0]
            value = "\n".join(lines[1:]) if len(lines) > 1 else ""
            sections[key] = value

        return sections

    @staticmethod
    def _parse_interface_config(output: str, ifname: str) -> DeviceConfig:
        """从 display current-configuration interface 输出中解析接口配置为键值对。"""
        config = DeviceConfig()
        config.set("interface_name", ifname)

        desc_match = re.search(r"^\s*description\s+(.+)", output, re.MULTILINE)
        if desc_match:
            config.set("description", desc_match.group(1).strip())

        if "shutdown" in output and "undo shutdown" not in output:
            config.set("admin_up", False)
        else:
            config.set("admin_up", True)

        link_match = re.search(r"port link-type\s+(\w+)", output)
        if link_match:
            config.set("link_type", link_match.group(1))

        access_match = re.search(r"port default vlan\s+(\d+)", output)
        if access_match:
            config.set("access_vlan", int(access_match.group(1)))

        trunk_match = re.search(r"port trunk allow-pass vlan\s+(.+)", output)
        if trunk_match:
            vlan_str = trunk_match.group(1).strip()
            config.set("trunk_allowed_vlans", HuaweiDevice._parse_vlan_list(vlan_str))

        return config

    @staticmethod
    def _parse_vlan_list(vlan_str: str) -> list[int]:
        """从字符串解析 VLAN 列表，支持空格、逗号分隔及范围表示。"""
        vlans: list[int] = []
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

    @staticmethod
    def _parse_lldp_neighbors(output: str) -> list[tuple[str, str]]:
        """解析 display lldp neighbor brief 输出，返回 (设备名, IP) 二元组列表。

        支持标准表格式输出：
            Local Intf   Neighbor Dev   Neighbor Intf   Neighbor IP
            GE0/0/0      S5700          GE0/0/1         10.1.1.2
        """
        neighbors: list[tuple[str, str]] = []
        lines = output.strip().splitlines()

        # 查找表头行，确定列位置
        header_idx = -1
        dev_col = -1
        ip_col = -1
        for i, line in enumerate(lines):
            lower = line.lower()
            if "neighbor dev" in lower and "neighbor ip" in lower:
                header_idx = i
                tokens = line.split()
                for j, token in enumerate(tokens):
                    if "dev" in token.lower():
                        dev_col = j
                    if "ip" in token.lower() and "neighbor" not in token.lower():
                        ip_col = j
                # 回退：按标准列顺序
                if dev_col < 0:
                    dev_col = 1
                if ip_col < 0:
                    ip_col = 3
                break

        if header_idx < 0:
            return neighbors

        for line in lines[header_idx + 1:]:
            tokens = line.split()
            if len(tokens) <= max(dev_col, ip_col):
                continue
            dev_name = tokens[dev_col]
            ip_addr = tokens[ip_col]
            # 简单校验 IP 格式
            if re.match(r"\d+\.\d+\.\d+\.\d+", ip_addr):
                neighbors.append((dev_name, ip_addr))

        return neighbors
