from __future__ import annotations

import re
from typing import Any


class HuaweiVRPParser:
    def parse_vlan_display(self, output: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "exists": False,
            "data": {},
        }

        vlan_pattern = re.compile(r"^\s*(\d+)\s+(\S*)\s+(.+)$", re.MULTILINE)
        match = vlan_pattern.search(output)

        if match:
            result["exists"] = True
            result["data"] = {
                "vlan_id": int(match.group(1)),
                "name": match.group(2).strip() or None,
                "description": match.group(3).strip(),
                "interfaces": self._extract_vlan_interfaces(output),
            }

        return result

    def _extract_vlan_interfaces(self, output: str) -> list[str]:
        interfaces: list[str] = []
        iface_pattern = re.compile(r"(GigabitEthernet\S+|Ethernet\S+|Serial\S+)")
        for match in iface_pattern.finditer(output):
            interfaces.append(match.group(1))
        return list(set(interfaces))

    def parse_interface_display(self, output: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "exists": False,
            "data": {},
        }

        result["exists"] = "interface" in output.lower() or "GigabitEthernet" in output

        if not result["exists"]:
            return result

        data: dict[str, Any] = {}

        admin_up_match = re.search(r"admin state is (\w+)", output, re.IGNORECASE)
        if admin_up_match:
            data["admin_up"] = admin_up_match.group(1).lower() == "up"

        desc_match = re.search(r"description\s+(.+)", output, re.IGNORECASE)
        if desc_match:
            data["description"] = desc_match.group(1).strip().strip('"')

        link_type_match = re.search(r"port link-type (\w+)", output, re.IGNORECASE)
        if link_type_match:
            data["link_type"] = link_type_match.group(1).lower()

        access_vlan_match = re.search(r"port default vlan (\d+)", output, re.IGNORECASE)
        if access_vlan_match:
            data["access_vlan"] = int(access_vlan_match.group(1))

        trunk_vlans_match = re.search(r"port trunk allow-pass vlan (.+)", output, re.IGNORECASE)
        if trunk_vlans_match:
            vlan_str = trunk_vlans_match.group(1).strip()
            vlans: list[int] = []
            for part in vlan_str.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    vlans.extend(range(int(start), int(end) + 1))
                elif part.isdigit():
                    vlans.append(int(part))
            data["trunk_allowed_vlans"] = vlans

        result["data"] = data
        return result

    def parse_system_view_prompt(self, output: str) -> bool:
        return "[" in output and "]" in output

    def parse_command_output(self, output: str) -> dict[str, Any]:
        success = "Error" not in output and "error" not in output.lower()
        return {
            "success": success,
            "raw_output": output,
            "error_detected": not success,
        }

    def parse_device_facts(self, output: str) -> dict[str, Any]:
        facts: dict[str, Any] = {}

        hostname_match = re.search(r"Hostname\s*:\s*(.+)", output)
        if hostname_match:
            facts["hostname"] = hostname_match.group(1).strip()

        model_match = re.search(r"Model\s*:\s*(.+)", output)
        if model_match:
            facts["model"] = model_match.group(1).strip()

        version_match = re.search(r"Version\s*:\s*(.+)", output)
        if version_match:
            facts["firmware_version"] = version_match.group(1).strip()

        serial_match = re.search(r"Serial\s*:\s*(.+)", output)
        if serial_match:
            facts["serial_number"] = serial_match.group(1).strip()

        uptime_match = re.search(r"Uptime\s*:\s*(.+)", output)
        if uptime_match:
            facts["uptime"] = uptime_match.group(1).strip()

        facts["vendor"] = "HUAWEI"
        return facts

    def parse_connection_test(self, output: str, elapsed_ms: int = 0) -> dict[str, Any]:
        success = "Error" not in output and "failed" not in output.lower()
        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
            "response_time_ms": elapsed_ms,
            "error_type": None if success else "CONNECTION_FAILED",
        }
