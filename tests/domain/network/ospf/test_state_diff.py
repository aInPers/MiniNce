from __future__ import annotations

from minince.domain.network.ospf.models import (
    OspfAuthType,
    OspfInterfaceIntent,
    OspfNetworkIntent,
    OspfOperation,
    OspfProcessIntent,
)
from minince.domain.network.ospf.state import (
    OspfAreaState,
    OspfInterfaceState,
    OspfProcessState,
    compute_diff,
)


def _present_intent(**kwargs) -> OspfProcessIntent:
    defaults = {"process_id": 1}
    defaults.update(kwargs)
    return OspfProcessIntent(**defaults)


class TestStateDiff:
    def test_same_state_no_changes(self) -> None:
        intent = _present_intent(
            router_id="10.255.0.1",
            networks=[OspfNetworkIntent(network="10.10.10.0/24", area_id="0.0.0.0")],
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1",
                    area_id="0.0.0.0",
                    cost=10,
                    network_type=None,
                )
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            router_id="10.255.0.1",
            areas={
                "0.0.0.0": OspfAreaState(area_id="0.0.0.0", networks=["10.10.10.0/24"]),
            },
            interfaces={
                "GigabitEthernet0/0/1": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/1",
                    area_id="0.0.0.0",
                    cost=10,
                )
            },
        )
        diff = compute_diff(intent, current)
        assert diff.changed is False
        assert diff.networks_to_add == []
        assert diff.networks_to_remove == []
        assert diff.interfaces_to_disable == []

    def test_new_network_only_generates_add(self) -> None:
        intent = _present_intent(
            networks=[
                OspfNetworkIntent(network="10.10.10.0/24", area_id="0.0.0.0"),
                OspfNetworkIntent(network="10.20.20.0/24", area_id="0.0.0.0"),
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            areas={
                "0.0.0.0": OspfAreaState(area_id="0.0.0.0", networks=["10.10.10.0/24"]),
            },
        )
        diff = compute_diff(intent, current)
        assert diff.networks_to_add == [("10.20.20.0/24", "0.0.0.0")]
        assert diff.networks_to_remove == []
        assert diff.changed is True

    def test_remove_single_network_keeps_process(self) -> None:
        """删除单个网段只产生 remove，不标记进程删除。"""
        intent = _present_intent(
            networks=[OspfNetworkIntent(network="10.10.10.0/24", area_id="0.0.0.0")],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            areas={
                "0.0.0.0": OspfAreaState(
                    area_id="0.0.0.0",
                    networks=["10.10.10.0/24", "10.20.20.0/24"],
                ),
            },
        )
        diff = compute_diff(intent, current)
        assert diff.networks_to_remove == [("10.20.20.0/24", "0.0.0.0")]
        assert diff.process_needs_delete is False
        assert diff.process_needs_create is False

    def test_router_id_change_flagged_with_warning(self) -> None:
        intent = _present_intent(router_id="10.255.0.2")
        current = OspfProcessState(process_id=1, running=True, router_id="10.255.0.1")
        diff = compute_diff(intent, current)
        assert diff.router_id_changed is True
        assert any("Router ID" in w for w in diff.warnings)

    def test_ensure_absent_marks_process_delete(self) -> None:
        intent = _present_intent(operation=OspfOperation.ENSURE_ABSENT)
        current = OspfProcessState(process_id=1, running=True, router_id="10.255.0.1")
        diff = compute_diff(intent, current)
        assert diff.process_needs_delete is True
        assert diff.changed is True

    def test_ensure_absent_when_not_exists(self) -> None:
        intent = _present_intent(operation=OspfOperation.ENSURE_ABSENT)
        current = OspfProcessState.empty(1)
        diff = compute_diff(intent, current)
        assert diff.process_needs_delete is False
        assert diff.changed is False

    def test_new_interface_needs_enable(self) -> None:
        intent = _present_intent(
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1", area_id="0.0.0.0", cost=10
                )
            ],
        )
        current = OspfProcessState(process_id=1, running=True)
        diff = compute_diff(intent, current)
        assert len(diff.interfaces_to_configure) == 1
        iface_diff = diff.interfaces_to_configure[0]
        assert iface_diff.needs_enable is True
        assert iface_diff.cost_changed is True

    def test_interface_area_change_needs_reenable(self) -> None:
        intent = _present_intent(
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1", area_id="0.0.0.1"
                )
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/1": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/1", area_id="0.0.0.0"
                )
            },
        )
        diff = compute_diff(intent, current)
        iface_diff = diff.interfaces_to_configure[0]
        assert iface_diff.area_changed is True
        assert iface_diff.needs_enable is True

    def test_interface_disable_when_not_in_intent(self) -> None:
        intent = _present_intent()
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/9": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/9", area_id="0.0.0.0"
                )
            },
        )
        diff = compute_diff(intent, current)
        assert diff.interfaces_to_disable == ["GigabitEthernet0/0/9"]

    def test_silent_reconciliation(self) -> None:
        intent = _present_intent(
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1", area_id="0.0.0.0", silent=True
                ),
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/2", area_id="0.0.0.0", silent=False
                ),
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/1": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/1", area_id="0.0.0.0"
                ),
                "GigabitEthernet0/0/2": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/2", area_id="0.0.0.0"
                ),
            },
            silent_interfaces={"GigabitEthernet0/0/2"},
        )
        diff = compute_diff(intent, current)
        assert diff.silent_to_add == ["GigabitEthernet0/0/1"]
        assert diff.silent_to_remove == ["GigabitEthernet0/0/2"]

    def test_auth_change_detected(self) -> None:
        from minince.domain.network.ospf.models import OspfAuthType

        intent = _present_intent(
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1",
                    area_id="0.0.0.0",
                    auth_type=OspfAuthType.HMAC_MD5,
                    auth_key_id=1,
                    auth_secret="secret",
                )
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/1": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/1",
                    area_id="0.0.0.0",
                    auth_type="none",
                )
            },
        )
        diff = compute_diff(intent, current)
        assert diff.interfaces_to_configure[0].auth_changed is True

    def test_process_create_when_not_running(self) -> None:
        intent = _present_intent(router_id="10.255.0.1")
        current = OspfProcessState.empty(1)
        diff = compute_diff(intent, current)
        assert diff.process_needs_create is True
        # 进程新建时 router-id 随创建下发，不单独标记变更
        assert diff.router_id_changed is False
