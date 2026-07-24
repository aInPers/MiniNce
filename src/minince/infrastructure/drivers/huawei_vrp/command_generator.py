from __future__ import annotations

from typing import Any

from minince.domain.network.config_plan import ConfigPlan, ConfigStep
from minince.shared.enums import RiskLevel


class HuaweiVRPCommandGenerator:
    SYSTEM_VIEW_ENTER = "system-view"
    SYSTEM_VIEW_EXIT = "return"
    SAVE_CONFIG = "save"

    def generate_vlan_commands(
        self,
        intent: dict[str, Any],
        current_state: dict[str, Any] | None = None,
    ) -> ConfigPlan:
        operation = intent.get("operation", "create")
        vlan_id = intent.get("vlan_id", 0)
        name = intent.get("name")
        description = intent.get("description")

        current = current_state or {}
        vlan_exists = current.get("exists", False)
        current_data = current.get("data", {})

        steps: list[ConfigStep] = []
        commands: list[str] = []
        verify_commands: list[str] = []
        warnings: list[str] = []
        changed = False

        if operation == "create":
            if vlan_exists:
                changed = self._needs_vlan_update(vlan_id, name, description, current_data)
                if not changed:
                    steps.append(ConfigStep(
                        name="check_existing",
                        command=f"display vlan {vlan_id}",
                        description=f"VLAN {vlan_id} already exists with desired settings",
                    ))
                    return ConfigPlan(
                        device_id=int(intent.get("device_id", 0)),
                        feature="VLAN",
                        intent=intent,
                        current_state=current,
                        commands=[],
                        verify_commands=[f"display vlan {vlan_id}"],
                        changed=False,
                        risk_level=RiskLevel.LOW,
                        warnings=[],
                        steps=steps,
                    )
                commands, steps = self._generate_vlan_update(vlan_id, name, description, current_data)
            else:
                changed = True
                commands, steps = self._generate_vlan_create(vlan_id, name, description)

        elif operation == "update":
            if not vlan_exists:
                warnings.append(f"VLAN {vlan_id} does not exist, creating instead")
                changed = True
                commands, steps = self._generate_vlan_create(vlan_id, name, description)
            else:
                changed = self._needs_vlan_update(vlan_id, name, description, current_data)
                if changed:
                    commands, steps = self._generate_vlan_update(vlan_id, name, description, current_data)
                else:
                    steps.append(ConfigStep(
                        name="check_existing",
                        command=f"display vlan {vlan_id}",
                        description=f"VLAN {vlan_id} already matches desired settings",
                    ))

        elif operation == "delete":
            changed = vlan_exists
            if changed:
                commands.append(f"undo vlan {vlan_id}")
                steps.append(ConfigStep(
                    name="delete_vlan",
                    command=f"undo vlan {vlan_id}",
                    description=f"Delete VLAN {vlan_id}",
                ))
                warnings.append(f"Deleting VLAN {vlan_id} will remove all interfaces from this VLAN")
                warnings.append("This operation cannot be undone")
            else:
                steps.append(ConfigStep(
                    name="check_existing",
                    command=f"display vlan {vlan_id}",
                    description=f"VLAN {vlan_id} does not exist, nothing to delete",
                ))

        verify_commands.append(f"display vlan {vlan_id}")

        return ConfigPlan(
            device_id=int(intent.get("device_id", 0)),
            feature="VLAN",
            intent=intent,
            current_state=current,
            commands=commands,
            verify_commands=verify_commands,
            changed=changed,
            risk_level=self._get_vlan_risk_level(operation),
            warnings=warnings,
            steps=steps,
        )

    def _generate_vlan_create(
        self,
        vlan_id: int,
        name: str | None,
        description: str | None,
    ) -> tuple[list[str], list[ConfigStep]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []

        commands.append(f"vlan {vlan_id}")
        steps.append(ConfigStep(
            name="create_vlan",
            command=f"vlan {vlan_id}",
            description=f"Enter VLAN {vlan_id} view and create",
        ))

        if name:
            name_cmd = f" name {name}"
            commands.append(name_cmd)
            steps.append(ConfigStep(
                name="set_vlan_name",
                command=name_cmd,
                description=f"Set VLAN name to {name}",
            ))

        if description:
            desc_cmd = f" description {description}"
            commands.append(desc_cmd)
            steps.append(ConfigStep(
                name="set_vlan_description",
                command=desc_cmd,
                description="Set VLAN description",
            ))

        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_vlan_view",
            command="quit",
            description="Exit VLAN view",
        ))

        return commands, steps

    def _generate_vlan_update(
        self,
        vlan_id: int,
        name: str | None,
        description: str | None,
        current_data: dict[str, Any],
    ) -> tuple[list[str], list[ConfigStep]]:
        commands: list[str] = []
        steps: list[ConfigStep] = []

        commands.append(f"vlan {vlan_id}")
        steps.append(ConfigStep(
            name="enter_vlan_view",
            command=f"vlan {vlan_id}",
            description=f"Enter VLAN {vlan_id} view",
        ))

        current_name = current_data.get("name", "")
        if name and name != current_name:
            name_cmd = f" name {name}"
            commands.append(name_cmd)
            steps.append(ConfigStep(
                name="update_vlan_name",
                command=name_cmd,
                description=f"Update VLAN name from '{current_name}' to '{name}'",
            ))

        current_desc = current_data.get("description", "")
        if description and description != current_desc:
            desc_cmd = f" description {description}"
            commands.append(desc_cmd)
            steps.append(ConfigStep(
                name="update_vlan_description",
                command=desc_cmd,
                description="Update VLAN description",
            ))

        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_vlan_view",
            command="quit",
            description="Exit VLAN view",
        ))

        return commands, steps

    def _needs_vlan_update(
        self,
        vlan_id: int,
        name: str | None,
        description: str | None,
        current_data: dict[str, Any],
    ) -> bool:
        if name and name != current_data.get("name", ""):
            return True
        if description and description != current_data.get("description", ""):
            return True
        return False

    def _get_vlan_risk_level(self, operation: str) -> RiskLevel:
        if operation == "delete":
            return RiskLevel.HIGH
        elif operation == "update":
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def generate_interface_commands(
        self,
        intent: dict[str, Any],
        current_state: dict[str, Any] | None = None,
    ) -> ConfigPlan:
        ifname = intent.get("interface_name", "")
        description = intent.get("description")
        admin_up = intent.get("admin_up")
        link_type = intent.get("link_type")
        access_vlan = intent.get("access_vlan")
        trunk_allowed_vlans = intent.get("trunk_allowed_vlans")

        current = current_state or {}
        current_data = current.get("data", {})

        steps: list[ConfigStep] = []
        commands: list[str] = []
        verify_commands: list[str] = []
        warnings: list[str] = []
        changed = False

        steps.append(ConfigStep(
            name="enter_interface_view",
            command=f"interface {ifname}",
            description=f"Enter interface {ifname} view",
        ))

        commands.append(f"interface {ifname}")

        cur_desc = current_data.get("description")
        if description is not None and description != cur_desc:
            changed = True
            desc_cmd = f" description {description}"
            commands.append(desc_cmd)
            steps.append(ConfigStep(
                name="set_description",
                command=desc_cmd,
                description="Set interface description",
            ))

        cur_admin_up = current_data.get("admin_up")
        if admin_up is not None and admin_up != cur_admin_up:
            changed = True
            if admin_up:
                cmd = " undo shutdown"
            else:
                cmd = " shutdown"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_admin_state",
                command=cmd,
                description=f"{'Enable' if admin_up else 'Disable'} interface",
            ))
            if not admin_up:
                warnings.append(f"Disabling interface {ifname} will disrupt traffic")

        cur_link_type = current_data.get("link_type")
        if link_type and link_type != cur_link_type:
            changed = True
            if link_type == "access":
                cmd = " port link-type access"
            elif link_type == "trunk":
                cmd = " port link-type trunk"
            elif link_type == "hybrid":
                cmd = " port link-type hybrid"
            else:
                cmd = f" port link-type {link_type}"
            commands.append(cmd)
            steps.append(ConfigStep(
                name="set_link_type",
                command=cmd,
                description=f"Set link type to {link_type}",
            ))

        if link_type == "access" and access_vlan is not None:
            cur_access_vlan = current_data.get("access_vlan")
            if access_vlan != cur_access_vlan:
                changed = True
                cmd = f" port default vlan {access_vlan}"
                commands.append(cmd)
                steps.append(ConfigStep(
                    name="set_access_vlan",
                    command=cmd,
                    description=f"Set access VLAN to {access_vlan}",
                ))

        if link_type == "trunk" and trunk_allowed_vlans:
            cur_trunk_vlans = current_data.get("trunk_allowed_vlans", [])
            cur_set = set(cur_trunk_vlans) if cur_trunk_vlans else set()
            new_set = set(trunk_allowed_vlans)
            if cur_set != new_set:
                changed = True
                vlan_str = ",".join(str(v) for v in trunk_allowed_vlans)
                cmd = f" port trunk allow-pass vlan {vlan_str}"
                commands.append(cmd)
                steps.append(ConfigStep(
                    name="set_trunk_vlans",
                    command=cmd,
                    description=f"Set trunk allowed VLANs: {vlan_str}",
                ))

        commands.append("quit")
        steps.append(ConfigStep(
            name="exit_interface_view",
            command="quit",
            description="Exit interface view",
        ))

        verify_commands.append(f"display current-configuration interface {ifname}")

        if not changed:
            steps.insert(0, ConfigStep(
                name="check_existing",
                command=f"display current-configuration interface {ifname}",
                description=f"Interface {ifname} already matches desired settings",
            ))

        return ConfigPlan(
            device_id=int(intent.get("device_id", 0)),
            feature="INTERFACE",
            intent=intent,
            current_state=current,
            commands=commands if changed else [],
            verify_commands=verify_commands,
            changed=changed,
            risk_level=self._get_interface_risk_level(admin_up, link_type),
            warnings=warnings,
            steps=steps,
        )

    def _get_interface_risk_level(
        self,
        admin_up: bool | None,
        link_type: str | None,
    ) -> RiskLevel:
        if admin_up is False:
            return RiskLevel.HIGH
        if link_type in ("trunk", "hybrid"):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def generate_save_commands(self) -> list[str]:
        return [self.SAVE_CONFIG, "y"]
