from __future__ import annotations

from ipaddress import IPv4Network

from minince.domain.network.ospf.models import OspfProcessIntent
from minince.shared.exceptions import ValidationError


def validate_ospf_intent(intent: OspfProcessIntent) -> None:
    """对 OSPF 意图执行跨字段校验，失败时抛出 ValidationError。

    模型自身已完成单字段校验（Area ID 合法、接口名格式、认证参数匹配、接口唯一）。
    本函数负责跨字段约束：
    - 网段重复或重叠且归属不同 Area
    - ensure_absent 语义一致性
    - router_id / 网段字符串中的换行与命令分隔符注入
    """
    _check_no_injection(intent)
    _check_network_overlap(intent)
    _check_absent_semantics(intent)


def _check_no_injection(intent: OspfProcessIntent) -> None:
    forbidden = ("\n", "\r", ";", "|", "`", "$(")
    if intent.router_id is not None:
        rid = str(intent.router_id)
        if any(ch in rid for ch in forbidden):
            raise ValidationError(f"Router ID contains illegal characters: {rid!r}")
    for net in intent.networks:
        text = str(net.network)
        if any(ch in text for ch in forbidden):
            raise ValidationError(f"Network contains illegal characters: {text!r}")
        area = str(net.area_id)
        if any(ch in area for ch in forbidden):
            raise ValidationError(f"Area ID contains illegal characters: {area!r}")


def _check_network_overlap(intent: OspfProcessIntent) -> None:
    seen: list[tuple[IPv4Network, str]] = []
    for net in intent.networks:
        network = net.network
        area = str(net.area_id)
        # 同一网段重复声明
        for prev_net, prev_area in seen:
            if prev_net == network and prev_area == area:
                raise ValidationError(
                    f"Duplicate OSPF network {network} in area {area}",
                    details={"network": str(network), "area_id": area},
                )
            # 重叠但归属不同 Area 非法
            if prev_net.overlaps(network) and prev_area != area:
                raise ValidationError(
                    f"Overlapping OSPF networks {prev_net} and {network} belong to "
                    f"different areas ({prev_area} vs {area})",
                    details={
                        "network_a": str(prev_net),
                        "area_a": prev_area,
                        "network_b": str(network),
                        "area_b": area,
                    },
                )
        seen.append((network, area))


def _check_absent_semantics(intent: OspfProcessIntent) -> None:
    from minince.domain.network.ospf.models import OspfOperation

    if intent.operation == OspfOperation.ENSURE_ABSENT:
        if intent.networks or intent.interfaces:
            raise ValidationError(
                "ensure_absent deletes the whole OSPF process; "
                "networks and interfaces must be empty",
                details={"process_id": intent.process_id},
            )
