from __future__ import annotations

from minince.infrastructure.drivers.huawei_vrp.huawei_device import HuaweiDevice
from minince.shared.enums import ConnectionType, RiskLevel


def _intent(
    *,
    operation: str = "ensure_present",
    process_id: int = 1,
    router_id: str | None = "10.255.0.1",
    networks: list[dict] | None = None,
    interfaces: list[dict] | None = None,
    expected_neighbors: list[str] | None = None,
) -> dict:
    return {
        "feature": "OSPF",
        "operation": operation,
        "process_id": process_id,
        "router_id": router_id,
        "networks": networks or [],
        "interfaces": interfaces or [],
        "expected_neighbors": expected_neighbors,
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


class TestHuaweiOspfDriverLifecycle:
    def setup_method(self) -> None:
        self.driver = HuaweiDevice(
            host="mock:192.168.1.1", port=22, username="admin", password="test"
        )
        self.driver.connect(ConnectionType.SSH)

    def test_get_current_state_process_not_exists(self) -> None:
        state = self.driver.get_current_state(_intent())
        assert state.feature == "OSPF"
        assert state.exists is False

    def test_build_plan_create_process(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface(cost=10, network_type="p2p")],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)

        assert plan.feature == "OSPF"
        assert plan.changed is True
        assert "ospf 1 router-id 10.255.0.1" in plan.commands
        assert "  network 10.10.10.0 0.0.0.255" in plan.commands
        assert " ospf enable 1 area 0.0.0.0" in plan.commands

    def test_apply_plan_create_and_verify(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface(cost=10, network_type="p2p")],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True

        verify = self.driver.verify(intent)
        assert verify.success is True
        assert verify.details["process_running"] is True
        assert verify.details["interfaces_valid"] is True

    def test_idempotent_after_create(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface(cost=10)],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        state2 = self.driver.get_current_state(intent)
        plan2 = self.driver.build_plan(intent, state2)

        assert plan2.changed is False

    def test_delete_single_network_keeps_process(self) -> None:
        """删除单个网段不应删除进程。"""
        intent_create = _intent(
            networks=[
                {"network": "10.10.10.0/24", "area_id": "0.0.0.0"},
                {"network": "10.20.20.0/24", "area_id": "0.0.0.0"},
            ],
        )
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        intent_remove_one = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
        )
        state2 = self.driver.get_current_state(intent_remove_one)
        plan2 = self.driver.build_plan(intent_remove_one, state2)

        assert plan2.changed is True
        assert "  undo network 10.20.20.0 0.0.0.255" in plan2.commands
        assert "undo ospf 1" not in plan2.commands

        result = self.driver.apply_plan(plan2)
        assert result.success is True

        verify = self.driver.verify(intent_remove_one)
        assert verify.success is True

    def test_delete_process_via_ensure_absent(self) -> None:
        intent_create = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
        )
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        intent_delete = _intent(operation="ensure_absent", router_id=None)
        state2 = self.driver.get_current_state(intent_delete)
        plan2 = self.driver.build_plan(intent_delete, state2)

        assert plan2.changed is True
        assert plan2.commands == ["undo ospf 1"]
        assert plan2.risk_level == RiskLevel.HIGH

        result = self.driver.apply_plan(plan2)
        assert result.success is True

        verify = self.driver.verify(intent_delete)
        assert verify.success is True
        assert verify.details["status"] == "deleted"

    def test_router_id_change_is_high_risk(self) -> None:
        intent_create = _intent(router_id="10.255.0.1")
        state = self.driver.get_current_state(intent_create)
        plan = self.driver.build_plan(intent_create, state)
        self.driver.apply_plan(plan)

        intent_change = _intent(router_id="10.255.0.2")
        state2 = self.driver.get_current_state(intent_change)
        plan2 = self.driver.build_plan(intent_change, state2)

        assert plan2.risk_level == RiskLevel.HIGH
        assert " router-id 10.255.0.2" in plan2.commands

    def test_silent_interface(self) -> None:
        intent = _intent(
            interfaces=[_iface(name="GigabitEthernet0/0/2", silent=True)],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        verify = self.driver.verify(intent)
        assert verify.success is True

    def test_hmac_md5_auth(self) -> None:
        intent = _intent(
            interfaces=[
                _iface(
                    auth_type="hmac_md5",
                    auth_key_id=1,
                    auth_secret="supersecret",
                )
            ],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        result = self.driver.apply_plan(plan)

        assert result.success is True
        # 明文密码不应出现在执行输出的命令记录中（落库前由 TaskExecutor 脱敏，
        # 这里直接测试 apply 后的 verify 仍通过）
        verify = self.driver.verify(intent)
        assert verify.success is True

    def test_no_expected_neighbors_not_judged_as_failure(self) -> None:
        """无邻居预期时不会误判失败。"""
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        verify = self.driver.verify(intent)
        assert verify.success is True
        assert verify.details["neighbors_full"] is None

    def test_expected_neighbors_checked(self) -> None:
        """声明预期邻居但设备无邻居时验证失败。"""
        mock = self.driver._ssh_connection
        # 注入一个 Full 邻居
        if hasattr(mock, "add_ospf_peer"):
            mock.add_ospf_peer(1, "10.10.10.2", "10.10.10.2", "Full", "GigabitEthernet0/0/1")

        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface()],
            expected_neighbors=["10.10.10.2"],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        verify = self.driver.verify(intent)
        assert verify.success is True
        assert verify.details["neighbors_full"] is True

    def test_expected_neighbors_missing_fails(self) -> None:
        intent = _intent(
            networks=[{"network": "10.10.10.0/24", "area_id": "0.0.0.0"}],
            interfaces=[_iface()],
            expected_neighbors=["10.99.99.99"],
        )
        state = self.driver.get_current_state(intent)
        plan = self.driver.build_plan(intent, state)
        self.driver.apply_plan(plan)

        verify = self.driver.verify(intent)
        assert verify.success is False
        assert verify.details["neighbors_expected"] is False


class TestHuaweiOspfDriverSecretRedaction:
    def test_secret_not_in_command_outputs_after_apply(self) -> None:
        driver = HuaweiDevice(
            host="mock:192.168.1.1", port=22, username="admin", password="test"
        )
        driver.connect(ConnectionType.SSH)
        intent = _intent(
            interfaces=[
                _iface(
                    auth_type="simple",
                    auth_secret="supersecret",
                )
            ],
        )
        state = driver.get_current_state(intent)
        plan = driver.build_plan(intent, state)
        # 真实场景下 TaskExecutor 会在 apply 前对 plan.commands 脱敏；
        # 这里直接验证 renderer 的 redact 工具能清除密码
        from minince.infrastructure.drivers.huawei_vrp.ospf_renderer import HuaweiOspfRenderer

        secrets = HuaweiOspfRenderer.extract_secrets(intent)
        redacted_commands = HuaweiOspfRenderer.redact(plan.commands, secrets)
        blob = " ".join(redacted_commands)
        assert "supersecret" not in blob
        assert "********" in blob
