from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from minince.domain.network.ospf.state import (
    OspfAreaState,
    OspfInterfaceState,
    OspfProcessState,
)


class HuaweiOspfParser:
    """华为 VRP OSPF 显示命令解析器。

    将 display ospf brief / peer / interface / current-configuration configuration ospf
    的输出解析为标准化的 OspfProcessState。纯文本解析，无 I/O。
    """

    def parse_brief(self, output: str, process_id: int) -> tuple[bool, str | None]:
        """解析 display ospf brief，返回 (running, router_id)。"""
        if not output:
            return False, None

        running = False
        # "OSPF Process 1 with Router ID 10.255.0.1"
        header = re.search(
            rf"OSPF Process\s+{process_id}\s+with Router ID\s+(\S+)",
            output,
        )
        router_id: str | None = None
        if header:
            router_id = header.group(1)
            running = True
        else:
            # 仍可能匹配到进程头但进程 id 不同
            if re.search(rf"OSPF Process\s+{process_id}\b", output):
                running = True

        # 明确的关闭/未使能标志
        if re.search(r"is disabled|not enabled|not active", output, re.IGNORECASE):
            running = False
        return running, router_id

    def parse_running_config(self, output: str, process_id: int) -> OspfProcessState:
        """解析 display current-configuration configuration ospf，提取进程配置。"""
        state = OspfProcessState(process_id=process_id, running=True)
        if not output:
            state.running = False
            return state

        # 仅取目标进程段：从 "ospf {pid}" 到下一个顶层 "ospf " 或 "interface " 或 "return"
        process_block = self._extract_process_block(output, process_id)
        if process_block is None:
            # 配置中没有该进程段，视为进程不存在
            state.running = False
            return state

        self._fill_process_block(state, process_block)

        # 解析接口段中的 ospf 相关命令
        for iface_name, iface_block in self._extract_interface_blocks(output):
            self._fill_interface_block(state, iface_name, iface_block, process_id)

        return state

    def parse_peer(self, output: str) -> list[dict[str, Any]]:
        """解析 display ospf peer，返回邻居列表。"""
        peers: list[dict[str, Any]] = []
        if not output:
            return peers
        # 典型行：10.0.0.2  0  Full  GE0/0/1  10.0.0.1  ...
        # 兼容表头后的数据行
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("OSPF Process") or line.startswith("Area"):
                continue
            if line.startswith("RouterID") or line.startswith("Router ID"):
                continue
            # 抓取 Full/ExStart/Init/Exchange/Loading/2-Way 状态
            state_match = re.search(
                r"\b(Full|ExStart|Exchange|Loading|Init|2-Way|Down|Attempt)\b",
                line,
            )
            if state_match:
                # 抓取对端 IP（首列 IP）
                ip_match = re.match(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                peers.append(
                    {
                        "neighbor_id": ip_match.group(1) if ip_match else "",
                        "state": state_match.group(1),
                        "is_full": state_match.group(1) == "Full",
                        "raw": line,
                    }
                )
        return peers

    def parse_interface_display(self, output: str) -> list[dict[str, Any]]:
        """解析 display ospf interface，返回接口运行状态列表（用于验证交叉校验）。"""
        result: list[dict[str, Any]] = []
        if not output:
            return result
        # 每个接口段以 "GigabitEthernet..." 开头
        blocks = re.split(r"\n(?=\S+\s+is up|\S+\s+current state|Interface\s)", output)
        for block in blocks:
            if not block.strip():
                continue
            name_match = re.match(r"(\S+)", block.strip())
            if not name_match:
                continue
            name = name_match.group(1)
            area_match = re.search(r"Area\s+(\S+)", block)
            cost_match = re.search(r"Cost\s*[:\s]*(\d+)", block)
            type_match = re.search(r"Network Type\s*[:\s]*(\S+)", block)
            result.append(
                {
                    "interface_name": name,
                    "area_id": area_match.group(1) if area_match else None,
                    "cost": int(cost_match.group(1)) if cost_match else None,
                    "network_type": type_match.group(1).lower() if type_match else None,
                }
            )
        return result

    # ------------------------------------------------------------------
    # 内部解析
    # ------------------------------------------------------------------
    def _extract_process_block(self, output: str, process_id: int) -> str | None:
        """从配置输出中截取 `ospf {pid}` 进程段。"""
        pattern = re.compile(
            rf"(^|\n)\s*ospf\s+{process_id}\b(.*?)(?=\n\s*ospf\s+\d|\ninterface\s|\nreturn\b|\Z)",
            re.DOTALL,
        )
        match = pattern.search(output)
        if not match:
            return None
        return match.group(0)

    def _fill_process_block(self, state: OspfProcessState, block: str) -> None:
        # router-id
        rid_match = re.search(r"router-id\s+(\S+)", block)
        if rid_match:
            state.router_id = rid_match.group(1)

        current_area: str | None = None
        for line in block.splitlines():
            stripped = line.strip()
            area_match = re.match(r"area\s+(\S+)", stripped)
            if area_match:
                current_area = self._normalize_area(area_match.group(1))
                state.areas.setdefault(
                    current_area, OspfAreaState(area_id=current_area)
                )
                continue
            net_match = re.match(r"network\s+(\S+)\s+(\S+)", stripped)
            if net_match and current_area is not None:
                cidr = self._wildcard_to_cidr(net_match.group(1), net_match.group(2))
                if cidr:
                    state.areas[current_area].networks.append(cidr)
                continue
            silent_match = re.match(r"silent-interface\s+(\S+)", stripped)
            if silent_match:
                state.silent_interfaces.add(silent_match.group(1))
                continue
            # area 级认证
            auth_match = re.match(r"authentication-mode\s+(\S+)", stripped)
            if auth_match and current_area is not None:
                state.areas[current_area].auth_type = self._normalize_auth(
                    auth_match.group(1)
                )

    def _extract_interface_blocks(self, output: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        pattern = re.compile(
            r"(^|\n)\s*interface\s+(\S+)(.*?)(?=\ninterface\s|\nospf\s+\d|\nreturn\b|\Z)",
            re.DOTALL,
        )
        for match in pattern.finditer(output):
            name = match.group(2)
            body = match.group(0)
            blocks.append((name, body))
        return blocks

    def _fill_interface_block(
        self,
        state: OspfProcessState,
        iface_name: str,
        block: str,
        process_id: int,
    ) -> None:
        enable_match = re.search(
            rf"ospf enable\s+{process_id}\s+area\s+(\S+)", block
        )
        if not enable_match:
            return
        area = self._normalize_area(enable_match.group(1))
        iface = state.interfaces.setdefault(
            iface_name, OspfInterfaceState(interface_name=iface_name)
        )
        iface.area_id = area

        cost_match = re.search(r"ospf cost\s+(\d+)", block)
        if cost_match:
            iface.cost = int(cost_match.group(1))

        type_match = re.search(r"ospf network-type\s+(\S+)", block)
        if type_match:
            iface.network_type = type_match.group(1).lower()

        if re.search(r"ospf authentication-mode\s+hmac-md5", block):
            iface.auth_type = "hmac_md5"
            key_match = re.search(r"key-id\s+(\d+)", block)
            if key_match:
                iface.auth_key_id = int(key_match.group(1))
        elif re.search(r"ospf authentication-mode\s+simple", block):
            iface.auth_type = "simple"

    @staticmethod
    def _normalize_area(value: str) -> str:
        # 兼容 "0" 与 "0.0.0.0"
        if value.isdigit():
            return str(IPv4Address(int(value)))
        try:
            return str(IPv4Address(value))
        except ValueError:
            return value

    @staticmethod
    def _normalize_auth(token: str) -> str:
        token = token.lower()
        if "hmac" in token or "md5" in token:
            return "hmac_md5"
        if "simple" in token or "plain" in token:
            return "simple"
        return "none"

    @staticmethod
    def _wildcard_to_cidr(address: str, wildcard: str) -> str | None:
        try:
            wc = IPv4Address(wildcard)
            prefix = 32 - bin(int(wc)).count("1")
            if prefix < 0 or prefix > 32:
                return None
            net = IPv4Network(f"{address}/{prefix}", strict=False)
            return str(net)
        except (ValueError, TypeError):
            return None
