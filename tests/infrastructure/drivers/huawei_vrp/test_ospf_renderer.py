from __future__ import annotations

from minince.domain.network.ospf.state import (
    OspfAreaState,
    OspfInterfaceState,
    OspfProcessState,
)
from minince.infrastructure.drivers.huawei_vrp.ospf_renderer import HuaweiOspfRenderer
from minince.shared.enums import RiskLevel


def _intent(
    *,
    operation: str = "ensure_present",
    process_id: int = 1,
    router_id: str | None = "10.255.0.1",
    networks: list[dict] | None = None,
    interfaces: list[dict] | None = None,
) -> dict:
    return {
        "feature": "OSPF",
        "operation": operation,
        "process_id": process_id,
        "router_id": router_id,
        "networks": networks or [],
        "interfaces": interfaces or [],
    }


def _iface(
    name: str = "GigabitEthernet0/0/1",
    area: str = "0.0.0.0",
    cost: int | None = None,
    network_type: str | None = None,
    silent: bool = False,
    auth_type: str = "none",
    auth_key_id: int | None = None,
    auth_secret: str | None = None,
) -> dict:
    return {
        "interface_name": name,
        "area_id": area,
        "cost": cost,
        "network_type": network_type,
        "silent": silent,
        "auth_type": auth_type,
        "auth_key_id": auth_key_id,
        "auth_secret": auth_secret,
        "auth_secret_configured": bool(auth_secret),
        "auth_secret_encrypted": None,
    }


class TestOspfRendererPresent:
    def setup_method(self) -> None:
        self.renderer = HuaweiOspfRenderer()

    def test_new_process_generates_create_commands(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface(cost=10, network_type="p2p")],
        )
        plan = self.renderer.generate_commands(intent, {})

        assert plan.feature == "OSPF"
        assert plan.changed is True
        assert "ospf 1 router-id 10.255.0.1" in plan.commands
        assert "  network 10.10.10.0 0.0.0.255" in plan.commands
        assert " ospf enable 1 area 0.0.0.0" in plan.commands
        assert " ospf cost 10" in plan.commands
        assert " ospf network-type p2p" in plan.commands
        assert plan.risk_level == RiskLevel.MEDIUM

    def test_idempotent_same_state_no_commands(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface(cost=10)],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            router_id="10.255.0.1",
            areas={"0.0.0.0": OspfAreaState(area_id="0.0.0.0", networks=["10.10.10.0/24"])},
            interfaces={
                "GigabitEthernet0/0/1": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/1",
                    area_id="0.0.0.0",
                    cost=10,
                )
            },
        )
        plan = self.renderer.generate_commands(intent, current.to_dict())

        assert plan.changed is False
        assert plan.commands == []

    def test_add_network_only_generates_add_command(self) -> None:
        intent = _intent(
            networks=[
                {"network": "10.10.10.0/24", "area_id": "0.0.0.0"},
                {"network": "10.20.20.0/24", "area_id": "0.0.0.0"},
            ],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            router_id="10.255.0.1",
            areas={"0.0.0.0": OspfAreaState(area_id="0.0.0.0", networks=["10.10.10.0/24"])},
        )
        plan = self.renderer.generate_commands(intent, current.to_dict())

        assert plan.changed is True
        assert "  network 10.20.20.0 0.0.0.255" in plan.commands
        assert "  undo network" not in " ".join(plan.commands)

    def test_remove_single_network_does_not_delete_process(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
        )
        current = OspfProcessState(
            process_id=1,
            running=True,
            router_id="10.255.0.1",
            areas={
                "0.0.0.0": OspfAreaState(
                    area_id="0.0.0.0",
                    networks=["10.10.10.0/24", "10.20.20.0/24"],
                )
            },
        )
        plan = self.renderer.generate_commands(intent, current.to_dict())

        assert "  undo network 10.20.20.0 0.0.0.255" in plan.commands
        assert "undo ospf 1" not in plan.commands
        assert plan.risk_level == RiskLevel.HIGH

    def test_router_id_change_is_high_risk(self) -> None:
        intent = _intent(router_id="10.255.0.2")
        current = OspfProcessState(process_id=1, running=True, router_id="10.255.0.1")
        plan = self.renderer.generate_commands(intent, current.to_dict())

        assert plan.risk_level == RiskLevel.HIGH
        assert " router-id 10.255.0.2" in plan.commands
        assert any("Router ID" in w for w in plan.warnings)

    def test_silent_interface_command(self) -> None:
        intent = _intent(interfaces=[_iface(name="GigabitEthernet0/0/2", silent=True)])
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/2": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/2", area_id="0.0.0.0"
                )
            },
        )
        plan = self.renderer.generate_commands(intent, current.to_dict())
        assert " silent-interface GigabitEthernet0/0/2" in plan.commands

    def test_interface_disable_generates_undo(self) -> None:
        intent = _intent()
        current = OspfProcessState(
            process_id=1,
            running=True,
            interfaces={
                "GigabitEthernet0/0/9": OspfInterfaceState(
                    interface_name="GigabitEthernet0/0/9", area_id="0.0.0.0"
                )
            },
        )
        plan = self.renderer.generate_commands(intent, current.to_dict())
        assert "interface GigabitEthernet0/0/9" in plan.commands
        assert " undo ospf enable" in plan.commands
        assert plan.risk_level == RiskLevel.HIGH

    def test_verify_commands_present(self) -> None:
        plan = self.renderer.generate_commands(_intent(), {})
        assert "display ospf brief" in plan.verify_commands
        assert "display ospf peer" in plan.verify_commands
        assert "display current-configuration configuration ospf" in plan.verify_commands


class TestOspfRendererAbsent:
    def setup_method(self) -> None:
        self.renderer = HuaweiOspfRenderer()

    def test_delete_process_generates_undo_ospf(self) -> None:
        intent = _intent(operation="ensure_absent", router_id=None)
        current = OspfProcessState(process_id=1, running=True, router_id="10.255.0.1")
        plan = self.renderer.generate_commands(intent, current.to_dict())

        assert plan.changed is True
        assert plan.commands == ["undo ospf 1"]
        assert plan.risk_level == RiskLevel.HIGH

    def test_delete_when_not_exists_no_change(self) -> None:
        intent = _intent(operation="ensure_absent", router_id=None)
        plan = self.renderer.generate_commands(intent, {})
        assert plan.changed is False
        assert plan.commands == []


class TestOspfRendererAuthAndRedaction:
    def setup_method(self) -> None:
        self.renderer = HuaweiOspfRenderer()

    def test_hmac_md5_command_contains_secret(self) -> None:
        intent = _intent(
            interfaces=[
                _iface(
                    auth_type="hmac_md5",
                    auth_key_id=1,
                    auth_secret="supersecret",
                )
            ],
        )
        plan = self.renderer.generate_commands(intent, {})
        joined = " ".join(plan.commands)
        assert "cipher supersecret" in joined

    def test_secret_not_in_steps_or_intent_or_warnings(self) -> None:
        intent = _intent(
            interfaces=[
                _iface(
                    auth_type="simple",
                    auth_secret="supersecret",
                )
            ],
        )
        plan = self.renderer.generate_commands(intent, {})
        steps_blob = " ".join(s.command for s in plan.steps)
        warnings_blob = " ".join(plan.warnings)
        intent_blob = repr(plan.intent)
        assert "supersecret" not in steps_blob
        assert "supersecret" not in warnings_blob
        assert "supersecret" not in intent_blob
        # step 命令应使用 ******** 占位
        assert "********" in steps_blob

    def test_redact_replaces_secret(self) -> None:
        commands = [" ospf authentication-mode simple cipher supersecret"]
        redacted = HuaweiOspfRenderer.redact(commands, ["supersecret"])
        assert redacted == [" ospf authentication-mode simple cipher ********"]

    def test_redact_no_secrets_returns_copy(self) -> None:
        commands = ["ospf 1", "quit"]
        redacted = HuaweiOspfRenderer.redact(commands, [])
        assert redacted == commands
        assert redacted is not commands

    def test_extract_secrets(self) -> None:
        intent = _intent(
            interfaces=[
                _iface(auth_type="simple", auth_secret="s1"),
                _iface(name="GE0/0/2", auth_type="none"),
            ],
        )
        secrets = HuaweiOspfRenderer.extract_secrets(intent)
        assert secrets == ["s1"]

    def test_rollback_does_not_contain_secret(self) -> None:
        intent = _intent(
            interfaces=[
                _iface(
                    auth_type="hmac_md5",
                    auth_key_id=1,
                    auth_secret="supersecret",
                )
            ],
        )
        plan = self.renderer.generate_commands(intent, {})
        rollback_blob = " ".join(plan.rollback_commands)
        assert "supersecret" not in rollback_blob
