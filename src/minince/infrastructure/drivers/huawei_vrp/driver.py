from __future__ import annotations

import time
from typing import Any

from minince.domain.devices.driver import NetworkDeviceDriver
from minince.domain.devices.facts import ConnectionResult, CurrentState, DeviceFacts
from minince.domain.network.config_plan import ConfigPlan, ExecutionResult, VerificationResult
from minince.infrastructure.drivers.huawei_vrp.command_generator import HuaweiVRPCommandGenerator
from minince.infrastructure.drivers.huawei_vrp.parser import HuaweiVRPParser
from minince.shared.enums import RiskLevel


class HuaweiVRPDriver(NetworkDeviceDriver):
    def __init__(
        self,
        host: str = "",
        port: int = 22,
        username: str = "",
        password: str = "",
        enable_password: str = "",
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self._connected = False
        self._generator = HuaweiVRPCommandGenerator()
        self._parser = HuaweiVRPParser()
        self._simulated_state: dict[str, Any] = {}
        self._simulated_vlans: dict[int, dict[str, Any]] = {}
        self._simulated_interfaces: dict[str, dict[str, Any]] = {}
        self._context_stack: list[dict[str, Any]] = []
        self._current_vlan_id: int | None = None
        self._current_ifname: str | None = None

    def test_connection(self) -> ConnectionResult:
        start_time = time.time()
        response_time_ms = 0

        if not self.host:
            return ConnectionResult(
                success=False,
                message="No host configured",
                response_time_ms=0,
                error_type="NO_HOST",
            )

        try:
            self._connected = True
            response_time_ms = int((time.time() - start_time) * 1000)
            return ConnectionResult(
                success=True,
                message=f"Successfully connected to {self.host}:{self.port}",
                response_time_ms=response_time_ms,
            )
        except Exception as e:
            self._connected = False
            return ConnectionResult(
                success=False,
                message=str(e),
                response_time_ms=response_time_ms,
                error_type="CONNECTION_ERROR",
            )

    def get_facts(self) -> DeviceFacts:
        if not self._connected:
            result = self.test_connection()
            if not result.success:
                return DeviceFacts()

        return DeviceFacts(
            hostname=self._simulated_state.get("hostname", f"SW-{self.host.split('.')[-1] if self.host else 'UNKNOWN'}"),
            model=self._simulated_state.get("model", "S5720-28X-SI-AC"),
            firmware_version=self._simulated_state.get("firmware_version", "VRP (R) Software Version V200R023C00SPC600"),
            vendor="HUAWEI",
            serial_number=self._simulated_state.get("serial_number", ""),
            uptime=self._simulated_state.get("uptime", "0 days, 0:00:00"),
        )

    def get_current_state(self, intent: object) -> CurrentState:
        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._get_vlan_state(intent_dict)
        elif feature == "INTERFACE":
            return self._get_interface_state(intent_dict)
        else:
            return CurrentState(feature=feature, exists=False)

    def build_plan(
        self,
        intent: object,
        current_state: CurrentState,
    ) -> ConfigPlan:
        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._generator.generate_vlan_commands(intent_dict, current_state.to_dict())
        elif feature == "INTERFACE":
            return self._generator.generate_interface_commands(intent_dict, current_state.to_dict())
        else:
            return ConfigPlan(
                device_id=int(intent_dict.get("device_id", 0)),
                feature=feature,
                intent=intent_dict,
                current_state=current_state.to_dict(),
                commands=[],
                verify_commands=[],
                changed=False,
                risk_level=RiskLevel.LOW,
                warnings=[f"Unsupported feature: {feature}"],
            )

    def apply_plan(self, plan: ConfigPlan) -> ExecutionResult:
        if not self._connected:
            result = self.test_connection()
            if not result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to connect: {result.message}",
                )

        if not plan.changed:
            return ExecutionResult(
                success=True,
                command_outputs=[{"message": "No changes needed, configuration already matches desired state"}],
            )

        self._context_stack.clear()
        self._current_vlan_id = None
        self._current_ifname = None

        command_outputs: list[dict[str, Any]] = []
        commands_to_execute = [self._generator.SYSTEM_VIEW_ENTER] + plan.commands

        for cmd in commands_to_execute:
            output = self._execute_command(cmd)
            parsed = self._parser.parse_command_output(output)
            command_outputs.append({
                "command": cmd,
                "output": output,
                "success": parsed["success"],
            })
            if not parsed["success"]:
                return ExecutionResult(
                    success=False,
                    command_outputs=command_outputs,
                    error_message=f"Command failed: {cmd}",
                )

        self._save_config()

        return ExecutionResult(
            success=True,
            command_outputs=command_outputs,
        )

    def verify(self, intent: object) -> VerificationResult:
        intent_dict = self._to_dict(intent)
        feature = intent_dict.get("feature", "")

        if feature == "VLAN":
            return self._verify_vlan(intent_dict)
        elif feature == "INTERFACE":
            return self._verify_interface(intent_dict)
        else:
            return VerificationResult(
                success=False,
                error_message=f"Unsupported feature for verification: {feature}",
            )

    def _get_vlan_state(self, intent_dict: dict[str, Any]) -> CurrentState:
        vlan_id = intent_dict.get("vlan_id", 0)
        vlan_data = self._simulated_vlans.get(vlan_id)

        if vlan_data is None:
            return CurrentState(feature="VLAN", exists=False, data={})

        return CurrentState(
            feature="VLAN",
            exists=True,
            data={
                "vlan_id": vlan_id,
                "name": vlan_data.get("name", ""),
                "description": vlan_data.get("description", ""),
            },
        )

    def _get_interface_state(self, intent_dict: dict[str, Any]) -> CurrentState:
        ifname = intent_dict.get("interface_name", "")
        iface_data = self._simulated_interfaces.get(ifname)

        if iface_data is None:
            return CurrentState(feature="INTERFACE", exists=False, data={})

        return CurrentState(
            feature="INTERFACE",
            exists=True,
            data={
                "interface_name": ifname,
                "description": iface_data.get("description"),
                "admin_up": iface_data.get("admin_up", True),
                "link_type": iface_data.get("link_type"),
                "access_vlan": iface_data.get("access_vlan"),
                "trunk_allowed_vlans": iface_data.get("trunk_allowed_vlans", []),
            },
        )

    def _execute_command(self, command: str) -> str:
        cmd = command.strip()

        if cmd == self._generator.SYSTEM_VIEW_ENTER:
            self._context_stack.append({"type": "system"})
            return "Enter system view, return user view with return command."

        if cmd == "quit":
            if self._context_stack:
                ctx = self._context_stack.pop()
                if ctx["type"] == "vlan":
                    self._current_vlan_id = None
                elif ctx["type"] == "interface":
                    self._current_ifname = None
            if self._context_stack:
                parent = self._context_stack[-1]
                if parent["type"] == "vlan":
                    self._current_vlan_id = parent.get("vlan_id")
                elif parent["type"] == "interface":
                    self._current_ifname = parent.get("ifname")
            return "Return to previous view"

        if cmd.startswith("vlan "):
            vlan_id = int(cmd.split()[1])
            self._simulated_vlans.setdefault(vlan_id, {})
            self._context_stack.append({"type": "vlan", "vlan_id": vlan_id})
            self._current_vlan_id = vlan_id
            self._current_ifname = None
            return f"VLAN {vlan_id} view"

        if cmd.startswith("undo vlan "):
            vlan_id = int(cmd.split()[2])
            if vlan_id in self._simulated_vlans:
                del self._simulated_vlans[vlan_id]
            return "Info: The operation is successful."

        if cmd.startswith("name "):
            name = cmd.split(" ", 1)[1]
            if self._current_vlan_id is not None:
                vlan_data = self._simulated_vlans.get(self._current_vlan_id)
                if vlan_data is not None:
                    vlan_data["name"] = name
            return ""

        if cmd.startswith("description "):
            desc = cmd.split(" ", 1)[1]
            if self._current_vlan_id is not None:
                vlan_data = self._simulated_vlans.get(self._current_vlan_id)
                if vlan_data is not None:
                    vlan_data["description"] = desc
            elif self._current_ifname is not None:
                iface_data = self._simulated_interfaces.get(self._current_ifname)
                if iface_data is not None:
                    iface_data["description"] = desc
            return ""

        if cmd.startswith("interface "):
            ifname = cmd.split()[1]
            self._simulated_interfaces.setdefault(ifname, {"admin_up": True})
            self._context_stack.append({"type": "interface", "ifname": ifname})
            self._current_ifname = ifname
            self._current_vlan_id = None
            return f"Interface {ifname} view"

        if cmd == "undo shutdown":
            self._update_current_interface_field("admin_up", True)
            return ""

        if cmd == "shutdown":
            self._update_current_interface_field("admin_up", False)
            return ""

        if cmd.startswith("port link-type "):
            link_type = cmd.split()[-1]
            self._update_current_interface_field("link_type", link_type)
            return ""

        if cmd.startswith("port default vlan "):
            vlan_id = int(cmd.split()[-1])
            self._update_current_interface_field("access_vlan", vlan_id)
            return ""

        if cmd.startswith("port trunk allow-pass vlan "):
            vlan_str = cmd.split("vlan ", 1)[1]
            vlans: list[int] = []
            for part in vlan_str.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    vlans.extend(range(int(start), int(end) + 1))
                elif part.isdigit():
                    vlans.append(int(part))
            self._update_current_interface_field("trunk_allowed_vlans", vlans)
            return ""

        return ""

    def _update_current_interface_field(self, field: str, value: Any) -> None:
        if self._current_ifname is not None:
            iface_data = self._simulated_interfaces.get(self._current_ifname)
            if iface_data is not None:
                iface_data[field] = value

    def _save_config(self) -> None:
        pass

    def _to_dict(self, intent: object) -> dict[str, Any]:
        if isinstance(intent, dict):
            return intent
        if hasattr(intent, "model_dump"):
            return intent.model_dump()
        if hasattr(intent, "dict"):
            return intent.dict()
        return {"feature": str(intent)}

    def _verify_vlan(self, intent_dict: dict[str, Any]) -> VerificationResult:
        vlan_id = intent_dict.get("vlan_id", 0)
        expected_name = intent_dict.get("name")
        expected_desc = intent_dict.get("description")
        operation = intent_dict.get("operation", "create")

        vlan_data = self._simulated_vlans.get(vlan_id)

        if operation == "delete":
            if vlan_data is None:
                return VerificationResult(
                    success=True,
                    verification_outputs=[{"message": f"VLAN {vlan_id} successfully deleted"}],
                    details={"vlan_id": vlan_id, "status": "deleted"},
                )
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} still exists after delete operation",
                details={"vlan_id": vlan_id, "actual_state": vlan_data},
            )

        if vlan_data is None:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} not found after configuration",
                details={"vlan_id": vlan_id},
            )

        mismatches: list[str] = []
        if expected_name and vlan_data.get("name") != expected_name:
            mismatches.append(f"name mismatch: expected '{expected_name}', got '{vlan_data.get('name')}'")
        if expected_desc and vlan_data.get("description") != expected_desc:
            mismatches.append(f"description mismatch")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} verification failed: {'; '.join(mismatches)}",
                details={"vlan_id": vlan_id, "mismatches": mismatches, "actual_state": vlan_data},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"VLAN {vlan_id} verification passed"}],
            details={"vlan_id": vlan_id, "actual_state": vlan_data},
        )

    def _verify_interface(self, intent_dict: dict[str, Any]) -> VerificationResult:
        ifname = intent_dict.get("interface_name", "")
        expected_desc = intent_dict.get("description")
        expected_admin_up = intent_dict.get("admin_up")
        expected_link_type = intent_dict.get("link_type")
        expected_access_vlan = intent_dict.get("access_vlan")
        expected_trunk_vlans = intent_dict.get("trunk_allowed_vlans")

        iface_data = self._simulated_interfaces.get(ifname)

        if iface_data is None:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} not found after configuration",
                details={"interface_name": ifname},
            )

        mismatches: list[str] = []

        if expected_desc is not None and iface_data.get("description") != expected_desc:
            mismatches.append(f"description mismatch")
        if expected_admin_up is not None and iface_data.get("admin_up") != expected_admin_up:
            mismatches.append(f"admin state mismatch")
        if expected_link_type is not None and iface_data.get("link_type") != expected_link_type:
            mismatches.append(f"link type mismatch: expected {expected_link_type}, got {iface_data.get('link_type')}")
        if expected_access_vlan is not None and iface_data.get("access_vlan") != expected_access_vlan:
            mismatches.append(f"access VLAN mismatch")
        if expected_trunk_vlans is not None:
            actual_trunk = set(iface_data.get("trunk_allowed_vlans", []))
            expected_trunk = set(expected_trunk_vlans)
            if actual_trunk != expected_trunk:
                mismatches.append(f"trunk VLAN mismatch")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} verification failed: {'; '.join(mismatches)}",
                details={"interface_name": ifname, "mismatches": mismatches, "actual_state": iface_data},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"Interface {ifname} verification passed"}],
            details={"interface_name": ifname, "actual_state": iface_data},
        )