from __future__ import annotations

import re
import time
from typing import Any

from minince.domain.devices.driver import NetworkDeviceDriver
from minince.domain.devices.facts import ConnectionResult, CurrentState, DeviceFacts
from minince.domain.network.config_plan import ConfigPlan, ExecutionResult, VerificationResult
from minince.infrastructure.drivers.huawei_vrp.command_generator import HuaweiVRPCommandGenerator
from minince.infrastructure.drivers.huawei_vrp.parser import HuaweiVRPParser
from minince.infrastructure.ssh.base import SSHConfig, SSHConnection
from minince.infrastructure.ssh.mock_connection import MockSSHConnection
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
        ssh_connection: SSHConnection | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self._ssh_connection = ssh_connection
        self._connected = False
        self._generator = HuaweiVRPCommandGenerator()
        self._parser = HuaweiVRPParser()
        self._simulated_state: dict[str, Any] = {}
        self._simulated_vlans: dict[int, dict[str, Any]] = {}
        self._simulated_interfaces: dict[str, dict[str, Any]] = {}
        self._context_stack: list[dict[str, Any]] = []
        self._current_vlan_id: int | None = None
        self._current_ifname: str | None = None

        if self._ssh_connection is None:
            ssh_config = SSHConfig(
                host=host or "mock",
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                device_type="",
                enable_password=enable_password,
            )
            self._ssh_connection = MockSSHConnection(ssh_config)

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
            self._ssh_connection.connect()
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

        try:
            output = self._ssh_connection.send_command("display version")
            return self._parse_version_output(output)
        except Exception:
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

    def get_running_config(self) -> str:
        if not self._connected:
            result = self.test_connection()
            if not result.success:
                return ""

        try:
            output = self._ssh_connection.send_command("display current-configuration")
            return output
        except Exception:
            return ""

    def backup_config(self, backup_path: str) -> bool:
        config = self.get_running_config()
        if not config:
            return False

        from pathlib import Path
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
        Path(backup_path).write_text(config, encoding="utf-8")
        return True

    def _get_vlan_state(self, intent_dict: dict[str, Any]) -> CurrentState:
        vlan_id = intent_dict.get("vlan_id", 0)

        try:
            output = self._ssh_connection.send_command(f"display vlan {vlan_id}")
            return self._parse_vlan_state_output(output, vlan_id)
        except Exception:
            pass

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

        try:
            output = self._ssh_connection.send_command(f"display interface {ifname}")
            return self._parse_interface_state_output(output, ifname)
        except Exception:
            pass

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
        return self._ssh_connection.send_command(cmd)

    def _save_config(self) -> None:
        try:
            self._ssh_connection.save_config()
        except Exception:
            pass

    def _to_dict(self, intent: object) -> dict[str, Any]:
        if isinstance(intent, dict):
            return intent
        if hasattr(intent, "model_dump"):
            return intent.model_dump()
        if hasattr(intent, "dict"):
            return intent.dict()
        return {"feature": str(intent)}

    def _parse_version_output(self, output: str) -> DeviceFacts:
        hostname_match = re.search(r"(\S+)\s+uptime", output)
        hostname = hostname_match.group(1) if hostname_match else self.host or "UNKNOWN"

        model_match = re.search(r"(\w+-\w+-\w+-\w+)", output)
        model = model_match.group(1) if model_match else "Unknown"

        version_match = re.search(r"Software,\s*Version\s+(.+)", output)
        firmware = version_match.group(1).strip() if version_match else "Unknown"

        return DeviceFacts(
            hostname=hostname,
            model=model,
            firmware_version=firmware,
            vendor="HUAWEI",
            serial_number="",
            uptime="0 days, 0:00:00",
        )

    def _parse_vlan_state_output(self, output: str, vlan_id: int) -> CurrentState:
        if "does not exist" in output.lower() or "error" in output.lower():
            return CurrentState(feature="VLAN", exists=False, data={})

        name_match = re.search(r"Name:\s*(\S+)", output)
        desc_match = re.search(r"Description:\s*(.+)", output)

        return CurrentState(
            feature="VLAN",
            exists=True,
            data={
                "vlan_id": vlan_id,
                "name": name_match.group(1) if name_match else "",
                "description": desc_match.group(1).strip() if desc_match else "",
            },
        )

    def _parse_interface_state_output(self, output: str, ifname: str) -> CurrentState:
        if "error" in output.lower() or "does not exist" in output.lower():
            return CurrentState(feature="INTERFACE", exists=False, data={})

        link_type_match = re.search(r"Link type:(\w+)", output)
        desc_match = re.search(r"Description:\s*(.+)", output)
        admin_up_match = re.search(r"line protocol is (\w+)", output)

        link_type = link_type_match.group(1) if link_type_match else "access"
        admin_up = True
        if admin_up_match:
            admin_up = admin_up_match.group(1).lower() == "up"

        access_vlan = None
        access_match = re.search(r"Access VLAN:\s*(\d+)", output)
        if access_match:
            access_vlan = int(access_match.group(1))

        trunk_vlans: list[int] = []
        trunk_match = re.search(r"Trunk allowed VLANs:\s*(.+)", output)
        if trunk_match:
            for v in trunk_match.group(1).split(","):
                v = v.strip()
                if v.isdigit():
                    trunk_vlans.append(int(v))

        return CurrentState(
            feature="INTERFACE",
            exists=True,
            data={
                "interface_name": ifname,
                "description": desc_match.group(1).strip() if desc_match else "",
                "admin_up": admin_up,
                "link_type": link_type,
                "access_vlan": access_vlan,
                "trunk_allowed_vlans": trunk_vlans,
            },
        )

    def _verify_vlan(self, intent_dict: dict[str, Any]) -> VerificationResult:
        vlan_id = intent_dict.get("vlan_id", 0)
        expected_name = intent_dict.get("name")
        expected_desc = intent_dict.get("description")
        operation = intent_dict.get("operation", "create")

        try:
            output = self._ssh_connection.send_command(f"display vlan {vlan_id}")
            return self._verify_vlan_from_output(output, vlan_id, expected_name, expected_desc, operation)
        except Exception:
            pass

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
            mismatches.append("description mismatch")

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

    def _verify_vlan_from_output(
        self,
        output: str,
        vlan_id: int,
        expected_name: str | None,
        expected_desc: str | None,
        operation: str,
    ) -> VerificationResult:
        if operation == "delete":
            if "does not exist" in output.lower():
                return VerificationResult(
                    success=True,
                    verification_outputs=[{"message": f"VLAN {vlan_id} successfully deleted"}],
                    details={"vlan_id": vlan_id, "status": "deleted"},
                )
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} still exists after delete operation",
                details={"vlan_id": vlan_id, "output": output[:200]},
            )

        if "does not exist" in output.lower():
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} not found after configuration",
                details={"vlan_id": vlan_id},
            )

        mismatches: list[str] = []
        name_match = re.search(r"Name:\s*(\S+)", output)
        desc_match = re.search(r"Description:\s*(.+)", output)

        if expected_name and name_match:
            actual_name = name_match.group(1)
            if actual_name != expected_name:
                mismatches.append(f"name mismatch: expected '{expected_name}', got '{actual_name}'")

        if expected_desc and desc_match:
            actual_desc = desc_match.group(1).strip()
            if actual_desc != expected_desc:
                mismatches.append(f"description mismatch: expected '{expected_desc}', got '{actual_desc}'")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"VLAN {vlan_id} verification failed: {'; '.join(mismatches)}",
                details={"vlan_id": vlan_id, "mismatches": mismatches},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"VLAN {vlan_id} verification passed"}],
            details={"vlan_id": vlan_id},
        )

    def _verify_interface(self, intent_dict: dict[str, Any]) -> VerificationResult:
        ifname = intent_dict.get("interface_name", "")
        expected_desc = intent_dict.get("description")
        expected_admin_up = intent_dict.get("admin_up")
        expected_link_type = intent_dict.get("link_type")
        expected_access_vlan = intent_dict.get("access_vlan")
        expected_trunk_vlans = intent_dict.get("trunk_allowed_vlans")

        try:
            output = self._ssh_connection.send_command(f"display interface {ifname}")
            return self._verify_interface_from_output(
                output, ifname, expected_desc, expected_admin_up,
                expected_link_type, expected_access_vlan, expected_trunk_vlans,
            )
        except Exception:
            pass

        iface_data = self._simulated_interfaces.get(ifname)

        if iface_data is None:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} not found after configuration",
                details={"interface_name": ifname},
            )

        mismatches: list[str] = []

        if expected_desc is not None and iface_data.get("description") != expected_desc:
            mismatches.append("description mismatch")
        if expected_admin_up is not None and iface_data.get("admin_up") != expected_admin_up:
            mismatches.append("admin state mismatch")
        if expected_link_type is not None and iface_data.get("link_type") != expected_link_type:
            mismatches.append(f"link type mismatch: expected {expected_link_type}, got {iface_data.get('link_type')}")
        if expected_access_vlan is not None and iface_data.get("access_vlan") != expected_access_vlan:
            mismatches.append("access VLAN mismatch")
        if expected_trunk_vlans is not None:
            actual_trunk = set(iface_data.get("trunk_allowed_vlans", []))
            expected_trunk = set(expected_trunk_vlans)
            if actual_trunk != expected_trunk:
                mismatches.append("trunk VLAN mismatch")

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

    def _verify_interface_from_output(
        self,
        output: str,
        ifname: str,
        expected_desc: str | None,
        expected_admin_up: bool | None,
        expected_link_type: str | None,
        expected_access_vlan: int | None,
        expected_trunk_vlans: list[int] | None,
    ) -> VerificationResult:
        if "error" in output.lower() or "does not exist" in output.lower():
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} not found after configuration",
                details={"interface_name": ifname},
            )

        mismatches: list[str] = []

        desc_match = re.search(r"Description:\s*(.+)", output)
        if expected_desc is not None and desc_match:
            actual_desc = desc_match.group(1).strip()
            if actual_desc != expected_desc:
                mismatches.append(f"description mismatch: expected '{expected_desc}', got '{actual_desc}'")

        admin_match = re.search(r"line protocol is (\w+)", output)
        if expected_admin_up is not None and admin_match:
            actual_up = admin_match.group(1).lower() == "up"
            if actual_up != expected_admin_up:
                mismatches.append(f"admin state mismatch: expected {'up' if expected_admin_up else 'down'}, got {'up' if actual_up else 'down'}")

        link_type_match = re.search(r"Link type:(\w+)", output)
        if expected_link_type is not None and link_type_match:
            actual_type = link_type_match.group(1)
            if actual_type != expected_link_type:
                mismatches.append(f"link type mismatch: expected {expected_link_type}, got {actual_type}")

        access_match = re.search(r"Access VLAN:\s*(\d+)", output)
        if expected_access_vlan is not None and access_match:
            actual_vlan = int(access_match.group(1))
            if actual_vlan != expected_access_vlan:
                mismatches.append(f"access VLAN mismatch: expected {expected_access_vlan}, got {actual_vlan}")

        if expected_trunk_vlans is not None:
            trunk_match = re.search(r"Trunk allowed VLANs:\s*(.+)", output)
            if trunk_match:
                actual_vlans = [int(v.strip()) for v in trunk_match.group(1).split(",") if v.strip().isdigit()]
                expected_set = set(expected_trunk_vlans)
                actual_set = set(actual_vlans)
                if actual_set != expected_set:
                    mismatches.append(f"trunk VLAN mismatch: expected {sorted(expected_set)}, got {sorted(actual_set)}")

        if mismatches:
            return VerificationResult(
                success=False,
                error_message=f"Interface {ifname} verification failed: {'; '.join(mismatches)}",
                details={"interface_name": ifname, "mismatches": mismatches},
            )

        return VerificationResult(
            success=True,
            verification_outputs=[{"message": f"Interface {ifname} verification passed"}],
            details={"interface_name": ifname},
        )
