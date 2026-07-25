from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from minince.domain.network.ospf.models import (
    OspfAuthType,
    OspfInterfaceIntent,
    OspfNetworkType,
    OspfOperation,
    OspfProcessIntent,
)


@dataclass
class OspfAreaState:
    """设备上单个 Area 的标准化状态。"""

    area_id: str  # 点分十进制
    networks: list[str] = field(default_factory=list)  # CIDR 字符串
    auth_type: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "area_id": self.area_id,
            "networks": list(self.networks),
            "auth_type": self.auth_type,
        }


@dataclass
class OspfInterfaceState:
    """设备上单个接口的 OSPF 标准化状态。"""

    interface_name: str
    area_id: str | None = None
    cost: int | None = None
    network_type: str | None = None
    silent: bool = False
    auth_type: str = "none"
    auth_key_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface_name": self.interface_name,
            "area_id": self.area_id,
            "cost": self.cost,
            "network_type": self.network_type,
            "silent": self.silent,
            "auth_type": self.auth_type,
            "auth_key_id": self.auth_key_id,
        }


@dataclass
class OspfProcessState:
    """设备上单个 OSPF 进程的标准化状态。"""

    process_id: int
    running: bool = False
    router_id: str | None = None
    areas: dict[str, OspfAreaState] = field(default_factory=dict)
    interfaces: dict[str, OspfInterfaceState] = field(default_factory=dict)
    silent_interfaces: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "running": self.running,
            "router_id": self.router_id,
            "areas": {aid: a.to_dict() for aid, a in self.areas.items()},
            "interfaces": {n: i.to_dict() for n, i in self.interfaces.items()},
            "silent_interfaces": sorted(self.silent_interfaces),
        }

    @classmethod
    def empty(cls, process_id: int) -> OspfProcessState:
        return cls(process_id=process_id, running=False)

    def network_area_map(self) -> dict[str, str]:
        """返回 cidr -> area_id 的映射。"""
        result: dict[str, str] = {}
        for area_id, area in self.areas.items():
            for cidr in area.networks:
                result[cidr] = area_id
        return result


@dataclass
class OspfInterfaceDiff:
    """单个接口的差异描述。"""

    interface_name: str
    needs_enable: bool = False  # 接口尚未启用 OSPF，需要 ospf enable
    area_changed: bool = False
    cost_changed: bool = False
    network_type_changed: bool = False
    silent_changed: bool = False
    auth_changed: bool = False

    @property
    def needs_reconfigure(self) -> bool:
        return (
            self.needs_enable
            or self.area_changed
            or self.cost_changed
            or self.network_type_changed
            or self.auth_changed
        )


@dataclass
class OspfDiff:
    """设备无关的 OSPF 意图与当前状态差异。"""

    operation: str
    process_exists: bool
    process_needs_create: bool = False
    process_needs_delete: bool = False
    router_id_target: str | None = None
    router_id_changed: bool = False
    networks_to_add: list[tuple[str, str]] = field(default_factory=list)  # (cidr, area)
    networks_to_remove: list[tuple[str, str]] = field(default_factory=list)
    interfaces_to_configure: list[OspfInterfaceDiff] = field(default_factory=list)
    interfaces_to_disable: list[str] = field(default_factory=list)
    silent_to_add: list[str] = field(default_factory=list)
    silent_to_remove: list[str] = field(default_factory=list)
    changed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "process_exists": self.process_exists,
            "process_needs_create": self.process_needs_create,
            "process_needs_delete": self.process_needs_delete,
            "router_id_target": self.router_id_target,
            "router_id_changed": self.router_id_changed,
            "networks_to_add": [list(n) for n in self.networks_to_add],
            "networks_to_remove": [list(n) for n in self.networks_to_remove],
            "interfaces_to_configure": [
                {
                    "interface_name": d.interface_name,
                    "needs_enable": d.needs_enable,
                    "area_changed": d.area_changed,
                    "cost_changed": d.cost_changed,
                    "network_type_changed": d.network_type_changed,
                    "silent_changed": d.silent_changed,
                    "auth_changed": d.auth_changed,
                }
                for d in self.interfaces_to_configure
            ],
            "interfaces_to_disable": list(self.interfaces_to_disable),
            "silent_to_add": list(self.silent_to_add),
            "silent_to_remove": list(self.silent_to_remove),
            "changed": self.changed,
            "warnings": list(self.warnings),
        }


def compute_diff(
    intent: OspfProcessIntent,
    current: OspfProcessState,
) -> OspfDiff:
    """计算设备无关的差异。不生成任何厂商命令。"""
    operation = intent.operation.value
    process_exists = current.running
    diff = OspfDiff(operation=operation, process_exists=process_exists)

    if operation == OspfOperation.ENSURE_ABSENT.value:
        diff.process_needs_delete = process_exists
        diff.changed = process_exists
        if not process_exists:
            diff.warnings.append(
                f"OSPF process {intent.process_id} does not exist, nothing to delete"
            )
        return diff

    # ensure_present
    if not process_exists:
        diff.process_needs_create = True

    _diff_router_id(intent, current, diff)
    _diff_networks(intent, current, diff)
    _diff_interfaces(intent, current, diff)

    diff.changed = (
        diff.process_needs_create
        or diff.router_id_changed
        or bool(diff.networks_to_add)
        or bool(diff.networks_to_remove)
        or any(d.needs_reconfigure or d.silent_changed for d in diff.interfaces_to_configure)
        or bool(diff.interfaces_to_disable)
        or bool(diff.silent_to_add)
        or bool(diff.silent_to_remove)
    )
    return diff


def _diff_router_id(
    intent: OspfProcessIntent,
    current: OspfProcessState,
    diff: OspfDiff,
) -> None:
    target = str(intent.router_id) if intent.router_id else None
    diff.router_id_target = target
    if target is None:
        return
    if diff.process_needs_create:
        # 进程新建时 router-id 随创建命令一并下发，无需单独标记变更
        return
    if current.router_id is None or current.router_id != target:
        diff.router_id_changed = True
        diff.warnings.append(
            f"Router ID change to {target} may restart OSPF process or reset adjacencies"
        )


def _diff_networks(
    intent: OspfProcessIntent,
    current: OspfProcessState,
    diff: OspfDiff,
) -> None:
    current_map = current.network_area_map()

    intent_set: dict[str, str] = {}
    for net in intent.networks:
        cidr = str(net.network)
        area = str(net.area_id)
        intent_set[cidr] = area
        current_area = current_map.get(cidr)
        if current_area is None:
            diff.networks_to_add.append((cidr, area))
        elif current_area != area:
            # 同网段不同 Area：先删旧再加新
            diff.networks_to_remove.append((cidr, current_area))
            diff.networks_to_add.append((cidr, area))

    for cidr, area in current_map.items():
        if cidr not in intent_set:
            diff.networks_to_remove.append((cidr, area))


def _diff_interfaces(
    intent: OspfProcessIntent,
    current: OspfProcessState,
    diff: OspfDiff,
) -> None:
    intent_by_name = {i.interface_name: i for i in intent.interfaces}

    for name, iface_intent in intent_by_name.items():
        cur = current.interfaces.get(name)
        iface_diff = OspfInterfaceDiff(interface_name=name)

        if cur is None or cur.area_id is None:
            iface_diff.needs_enable = True
            iface_diff.area_changed = cur is not None and cur.area_id != str(iface_intent.area_id)
            iface_diff.cost_changed = iface_intent.cost is not None
            iface_diff.network_type_changed = iface_intent.network_type is not None
            iface_diff.silent_changed = iface_intent.silent
            iface_diff.auth_changed = iface_intent.auth_type != OspfAuthType.NONE
        else:
            target_area = str(iface_intent.area_id)
            if cur.area_id != target_area:
                iface_diff.area_changed = True
                iface_diff.needs_enable = True  # 切换 Area 需重新 ospf enable
            if iface_intent.cost is not None and cur.cost != iface_intent.cost:
                iface_diff.cost_changed = True
            if (
                iface_intent.network_type is not None
                and (cur.network_type or _net_type_str(iface_intent.network_type))
                != _net_type_str(iface_intent.network_type)
            ):
                iface_diff.network_type_changed = True
            # silent 在进程级别处理，但差异挂在接口上
            target_silent = iface_intent.silent
            cur_silent = name in current.silent_interfaces
            if target_silent != cur_silent:
                iface_diff.silent_changed = True
            # 认证：仅当 auth_type 明确不同才标记变更（密钥不可比对，保守不重下）
            if iface_intent.auth_type.value != (cur.auth_type or "none"):
                iface_diff.auth_changed = True

        diff.interfaces_to_configure.append(iface_diff)

    # 当前已启用但意图中不存在的接口 -> 禁用 OSPF
    for name, cur in current.interfaces.items():
        if name not in intent_by_name and cur.area_id is not None:
            diff.interfaces_to_disable.append(name)

    # silent 调和：独立于接口配置列表，便于进程视图下发 silent-interface
    intent_silent = {i.interface_name for i in intent.interfaces if i.silent}
    for name in intent_silent:
        if name not in current.silent_interfaces:
            diff.silent_to_add.append(name)
    for name in current.silent_interfaces:
        if name not in intent_silent:
            # 若接口将被禁用，silent 随之失效，无需单独 undo
            if name not in diff.interfaces_to_disable:
                diff.silent_to_remove.append(name)


def _net_type_str(value: OspfNetworkType | str | None) -> str:
    if value is None:
        return ""
    return value.value if isinstance(value, OspfNetworkType) else str(value)


def cidr_to_wildcard(cidr: str) -> str:
    """CIDR 转华为通配符掩码（设备相关辅助，供 renderer 复用）。"""
    net = IPv4Network(cidr, strict=False)
    wildcard = IPv4Address(int(net.netmask) ^ 0xFFFFFFFF)
    return f"{net.network_address} {wildcard}"
