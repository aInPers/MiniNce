from __future__ import annotations

from typing import Any

from minince.domain.network.config_plan import ConfigPlan, ConfigStep
from minince.domain.network.ospf.models import (
    OspfAuthType,
    OspfNetworkType,
    OspfOperation,
    OspfProcessIntent,
)
from minince.domain.network.ospf.state import (
    OspfDiff,
    OspfProcessState,
    cidr_to_wildcard,
    compute_diff,
)
from minince.shared.enums import RiskLevel


class HuaweiOspfRenderer:
    """华为 VRP OSPF 命令渲染器。

    职责：将设备无关的意图与当前状态差异翻译为 VRP 命令、风险等级、回滚命令与
    验证命令。不执行任何 I/O，不接触 SSH。明文认证密码仅用于生成 cipher 命令，
    不会写入 ConfigPlan.intent / warnings / steps 等可落库字段。
    """

    def generate_commands(
        self,
        intent_dict: dict[str, Any],
        current_state: dict[str, Any] | None = None,
    ) -> ConfigPlan:
        intent = OspfProcessIntent.from_structured(intent_dict)
        current = OspfProcessState.from_dict(current_state or {})
        diff = compute_diff(intent, current)

        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        warnings: list[str] = diff.warnings
        risk = RiskLevel.LOW

        if diff.operation == OspfOperation.ENSURE_ABSENT.value:
            commands, steps, risk = self._render_absent(intent, diff)
            rollback = []  # 删除进程的回滚需完整历史，第一版不声称支持
            warnings.append(
                "rollback_commands not generated for process deletion; "
                "restore manually from backup if needed"
            )
        else:
            commands, steps, risk, rollback = self._render_present(intent, diff, current)

        verify_commands = [
            "display ospf brief",
            "display ospf peer",
            "display ospf interface",
            "display current-configuration configuration ospf",
        ]

        if not diff.changed:
            steps.insert(
                0,
                ConfigStep(
                    name="check_existing",
                    command="display ospf brief",
                    description=f"OSPF process {intent.process_id} already matches desired state",
                ),
            )

        return ConfigPlan(
            device_id=int(intent_dict.get("device_id", 0)),
            feature="OSPF",
            intent=intent.to_structured_intent(auth_secret_encrypted=None),
            current_state=current.to_dict(),
            commands=commands,
            verify_commands=verify_commands,
            changed=diff.changed,
            risk_level=risk,
            warnings=warnings,
            steps=steps,
            rollback_commands=rollback,
        )

    # ------------------------------------------------------------------
    # ensure_absent
    # ------------------------------------------------------------------
    def _render_absent(
        self,
        intent: OspfProcessIntent,
        diff: OspfDiff,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel]:
        if not diff.process_needs_delete:
            return [], [], RiskLevel.LOW
        cmd = f"undo ospf {intent.process_id}"
        return [cmd], [
            ConfigStep(
                name="delete_process",
                command=cmd,
                description=f"Delete OSPF process {intent.process_id}",
            )
        ], RiskLevel.HIGH

    # ------------------------------------------------------------------
    # ensure_present
    # ------------------------------------------------------------------
    def _render_present(
        self,
        intent: OspfProcessIntent,
        diff: OspfDiff,
        current: OspfProcessState,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.LOW

        # 进程视图命令：进程创建/删除、router-id、网段、silent-interface
        process_cmds, process_steps, process_risk, process_rollback = self._render_process_view(
            intent, diff, current
        )
        commands.extend(process_cmds)
        steps.extend(process_steps)
        rollback.extend(process_rollback)
        risk = self._max_risk(risk, process_risk)

        # 接口视图命令：ospf enable / cost / network-type / auth
        iface_cmds, iface_steps, iface_risk, iface_rollback = self._render_interface_views(
            intent, diff
        )
        commands.extend(iface_cmds)
        steps.extend(iface_steps)
        rollback.extend(iface_rollback)
        risk = self._max_risk(risk, iface_risk)

        return commands, steps, risk, rollback

    def _render_process_view(
        self,
        intent: OspfProcessIntent,
        diff: OspfDiff,
        current: OspfProcessState,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.LOW

        needs_process_view = (
            diff.process_needs_create
            or diff.router_id_changed
            or bool(diff.networks_to_add)
            or bool(diff.networks_to_remove)
            or bool(diff.silent_to_add)
            or bool(diff.silent_to_remove)
        )
        if not needs_process_view:
            return commands, steps, risk, rollback

        # 进入 ospf 视图
        if diff.process_needs_create:
            if intent.router_id is not None:
                enter_cmd = f"ospf {intent.process_id} router-id {intent.router_id}"
            else:
                enter_cmd = f"ospf {intent.process_id}"
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
            rollback.append(f"undo ospf {intent.process_id}")
        else:
            enter_cmd = f"ospf {intent.process_id}"
        commands.append(enter_cmd)
        steps.append(ConfigStep(
            name="enter_ospf_view",
            command=enter_cmd,
            description=f"Enter OSPF process {intent.process_id} view",
        ))

        # router-id 变更（进程已存在）
        if diff.router_id_changed and not diff.process_needs_create:
            rid_cmd = f" router-id {diff.router_id_target}"
            commands.append(rid_cmd)
            steps.append(ConfigStep(
                name="set_router_id",
                command=rid_cmd,
                description=f"Change Router ID to {diff.router_id_target}",
            ))
            risk = self._max_risk(risk, RiskLevel.HIGH)
            if current.router_id:
                rollback.insert(0, f"ospf {intent.process_id}")
                rollback.insert(1, f" router-id {current.router_id}")
                rollback.insert(2, "quit")

        # 网段按 Area 分组
        add_by_area = self._group_by_area(diff.networks_to_add)
        remove_by_area = self._group_by_area(diff.networks_to_remove)

        all_areas = set(add_by_area) | set(remove_by_area)
        for area_id in sorted(all_areas):
            area_cmds, area_steps, area_risk, area_rollback = self._render_area(
                intent.process_id, area_id,
                add_by_area.get(area_id, []),
                remove_by_area.get(area_id, []),
            )
            commands.extend(area_cmds)
            steps.extend(area_steps)
            rollback.extend(area_rollback)
            risk = self._max_risk(risk, area_risk)

        # silent-interface（进程视图）
        for name in diff.silent_to_add:
            cmd = f" silent-interface {name}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="add_silent_interface",
                command=cmd,
                description=f"Silence OSPF on {name}",
            ))
            rollback.append(f"ospf {intent.process_id}")
            rollback.append(f" undo silent-interface {name}")
            rollback.append("quit")
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
        for name in diff.silent_to_remove:
            cmd = f" undo silent-interface {name}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="remove_silent_interface",
                command=cmd,
                description=f"Un-silence OSPF on {name}",
            ))
            risk = self._max_risk(risk, RiskLevel.MEDIUM)

        # 退出 ospf 视图
        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_ospf_view",
            command="quit",
            description="Exit OSPF process view",
        ))
        return commands, steps, risk, rollback

    def _render_area(
        self,
        process_id: int,
        area_id: str,
        to_add: list[str],
        to_remove: list[str],
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.LOW

        commands.append(f" area {area_id}")
        steps.append(ConfigStep(
            name="enter_area_view",
            command=f"area {area_id}",
            description=f"Enter area {area_id} view",
        ))

        for cidr in to_add:
            wc = cidr_to_wildcard(cidr)
            cmd = f"  network {wc}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="add_network",
                command=f"network {wc}",
                description=f"Publish {cidr} in area {area_id}",
            ))
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
            rollback.append(f"ospf {process_id}")
            rollback.append(f" area {area_id}")
            rollback.append(f"  undo network {wc}")
            rollback.append("quit")
            rollback.append("quit")

        for cidr in to_remove:
            wc = cidr_to_wildcard(cidr)
            cmd = f"  undo network {wc}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="remove_network",
                command=f"undo network {wc}",
                description=f"Withdraw {cidr} from area {area_id}",
            ))
            risk = self._max_risk(risk, RiskLevel.HIGH)
            rollback.append(f"ospf {process_id}")
            rollback.append(f" area {area_id}")
            rollback.append(f"  network {wc}")
            rollback.append("quit")
            rollback.append("quit")

        commands.append(" quit")
        steps.append(ConfigStep(
            name="exit_area_view",
            command="quit",
            description="Exit area view",
        ))
        return commands, steps, risk, rollback

    def _render_interface_views(
        self,
        intent: OspfProcessIntent,
        diff: OspfDiff,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.LOW

        intent_by_name = {i.interface_name: i for i in intent.interfaces}

        for iface_diff in diff.interfaces_to_configure:
            if not (iface_diff.needs_reconfigure):
                continue
            iface_intent = intent_by_name[iface_diff.interface_name]
            cmds, sts, r, rb = self._render_single_interface(intent.process_id, iface_diff, iface_intent)
            commands.extend(cmds)
            steps.extend(sts)
            rollback.extend(rb)
            risk = self._max_risk(risk, r)

        for name in diff.interfaces_to_disable:
            cmds, sts, r, rb = self._render_disable_interface(name)
            commands.extend(cmds)
            steps.extend(sts)
            rollback.extend(rb)
            risk = self._max_risk(risk, r)

        return commands, steps, risk, rollback

    def _render_single_interface(
        self,
        process_id: int,
        iface_diff: Any,
        iface_intent: Any,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.LOW

        enter_cmd = f"interface {iface_intent.interface_name}"
        commands.append(enter_cmd)
        steps.append(ConfigStep(
            name="enter_interface_view",
            command=enter_cmd,
            description=f"Enter interface {iface_intent.interface_name} view",
        ))

        if iface_diff.needs_enable:
            area = str(iface_intent.area_id)
            cmd = f" ospf enable {process_id} area {area}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="enable_ospf",
                command=f"ospf enable {process_id} area {area}",
                description=f"Enable OSPF on {iface_intent.interface_name} in area {area}",
            ))
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
            rollback.append(f"interface {iface_intent.interface_name}")
            rollback.append(" undo ospf enable")
            rollback.append("quit")

        if iface_diff.cost_changed and iface_intent.cost is not None:
            cmd = f" ospf cost {iface_intent.cost}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_cost",
                command=f"ospf cost {iface_intent.cost}",
                description=f"Set OSPF cost {iface_intent.cost} on {iface_intent.interface_name}",
            ))
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
            rollback.append(f"interface {iface_intent.interface_name}")
            rollback.append(" undo ospf cost")
            rollback.append("quit")

        if iface_diff.network_type_changed and iface_intent.network_type is not None:
            nt = self._network_type_token(iface_intent.network_type)
            cmd = f" ospf network-type {nt}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_network_type",
                command=f"ospf network-type {nt}",
                description=f"Set OSPF network type {nt} on {iface_intent.interface_name}",
            ))
            risk = self._max_risk(risk, RiskLevel.MEDIUM)
            rollback.append(f"interface {iface_intent.interface_name}")
            rollback.append(" undo ospf network-type")
            rollback.append("quit")

        if iface_diff.auth_changed:
            auth_cmds, auth_steps, auth_risk, auth_rollback = self._render_auth(iface_intent)
            commands.extend(auth_cmds)
            steps.extend(auth_steps)
            rollback.extend(auth_rollback)
            risk = self._max_risk(risk, auth_risk)

        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_interface_view",
            command="quit",
            description="Exit interface view",
        ))
        return commands, steps, risk, rollback

    def _render_auth(self, iface_intent: Any) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.HIGH

        # 切换认证模式前先 undo，避免模式叠加报错
        commands.append(" undo ospf authentication-mode")
        steps.append(ConfigStep(
            name="clear_auth",
            command="undo ospf authentication-mode",
            description=f"Clear existing OSPF auth on {iface_intent.interface_name}",
        ))
        rollback.append(f"interface {iface_intent.interface_name}")
        rollback.append(" undo ospf authentication-mode")
        rollback.append("quit")

        if iface_intent.auth_type == OspfAuthType.SIMPLE:
            cmd = f" ospf authentication-mode simple cipher {iface_intent.auth_secret}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_simple_auth",
                command="ospf authentication-mode simple cipher ********",
                description=f"Enable simple auth on {iface_intent.interface_name}",
            ))
        elif iface_intent.auth_type == OspfAuthType.HMAC_MD5:
            cmd = (
                f" ospf authentication-mode hmac-md5 key-id {iface_intent.auth_key_id} "
                f"cipher {iface_intent.auth_secret}"
            )
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_hmac_md5_auth",
                command=(
                    f"ospf authentication-mode hmac-md5 key-id {iface_intent.auth_key_id} "
                    f"cipher ********"
                ),
                description=f"Enable hmac-md5 auth (key-id {iface_intent.auth_key_id}) "
                f"on {iface_intent.interface_name}",
            ))
        return commands, steps, risk, rollback

    def _render_disable_interface(
        self,
        name: str,
    ) -> tuple[list[str], list[ConfigStep], RiskLevel, list[str]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []
        rollback: list[str] = []
        risk = RiskLevel.HIGH

        commands.append(f"interface {name}")
        steps.append(ConfigStep(
            name="enter_interface_view",
            command=f"interface {name}",
            description=f"Enter interface {name} view to disable OSPF",
        ))
        for cmd, sname, desc in [
            (" undo ospf enable", "disable_ospf", f"Disable OSPF on {name}"),
            (" undo ospf cost", "unset_cost", f"Unset OSPF cost on {name}"),
            (" undo ospf network-type", "unset_network_type", f"Unset OSPF network type on {name}"),
            (" undo ospf authentication-mode", "unset_auth", f"Unset OSPF auth on {name}"),
        ]:
            commands.append(cmd)
            steps.append(ConfigStep(name=sname, command=cmd.strip(), description=desc))
        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_interface_view",
            command="quit",
            description="Exit interface view",
        ))
        return commands, steps, risk, rollback

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def extract_secrets(intent_dict: dict[str, Any]) -> list[str]:
        """从意图字典中收集明文认证密码（已由 TaskExecutor 解密）。"""
        secrets: list[str] = []
        for raw in intent_dict.get("interfaces") or []:
            secret = raw.get("auth_secret")
            if secret:
                secrets.append(secret)
        return secrets

    @staticmethod
    def redact(commands: list[str], secrets: list[str]) -> list[str]:
        """将命令中的明文密码替换为 ********，用于落库/预览/日志。"""
        if not secrets:
            return list(commands)
        redacted = list(commands)
        for i, cmd in enumerate(redacted):
            for secret in secrets:
                if secret and secret in cmd:
                    redacted[i] = cmd.replace(secret, "********")
        return redacted

    @staticmethod
    def _group_by_area(items: list[tuple[str, str]]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for cidr, area in items:
            grouped.setdefault(area, []).append(cidr)
        return grouped

    @staticmethod
    def _network_type_token(value: OspfNetworkType | str) -> str:
        return value.value if isinstance(value, OspfNetworkType) else str(value)

    @staticmethod
    def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
        return a if a.severity_order >= b.severity_order else b
