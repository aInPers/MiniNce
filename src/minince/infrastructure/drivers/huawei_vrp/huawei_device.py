from __future__ import annotations

import re
import time
from typing import Any

from minince.domain.devices.config import DeviceConfig
from minince.domain.devices.facts import ConnectionResult
from minince.domain.devices.network_device import NetworkDevice
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
