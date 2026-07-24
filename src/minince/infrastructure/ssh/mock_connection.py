from __future__ import annotations

import re
from typing import Any

from minince.infrastructure.ssh.base import SSHConfig


class MockSSHConnection:
    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._command_history: list[str] = []
        self._simulated_vlans: dict[int, dict[str, Any]] = {}
        self._simulated_interfaces: dict[str, dict[str, Any]] = {}
        self._simulated_state: dict[str, Any] = {
            "hostname": "SW-MOCK",
            "model": "S5720-28X-SI-AC",
            "firmware_version": "VRP (R) Software Version V200R023C00SPC600",
            "serial_number": "",
        }
        self._context_stack: list[dict[str, Any]] = []
        self._current_vlan_id: int | None = None
        self._current_ifname: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        if not self._connected:
            raise ConnectionError("Not connected")

        cmd = command.strip()
        self._command_history.append(cmd)

        if cmd.startswith("display version"):
            return self._handle_display_version()

        if cmd.startswith("display vlan"):
            return self._handle_display_vlan(cmd)

        if cmd.startswith("display interface"):
            return self._handle_display_interface(cmd)

        if cmd.startswith("display current-configuration"):
            return self._handle_display_current_config()

        if cmd == "system-view" or cmd == "sys":
            self._context_stack.append({"type": "system"})
            return "Enter system view, return user view with return command."

        if cmd == "quit":
            self._handle_quit()
            return "Return to previous view"

        if cmd.startswith("vlan "):
            self._handle_vlan_cmd(cmd)
            return f"Info: VLAN {self._current_vlan_id} has been created."

        if cmd.startswith("undo vlan "):
            vlan_id = int(cmd.split()[2])
            if vlan_id in self._simulated_vlans:
                del self._simulated_vlans[vlan_id]
            return "Info: The operation is successful."

        if cmd.startswith("interface "):
            self._handle_interface_cmd(cmd)
            return f"Enter the interface view of {self._current_ifname}."

        if cmd.startswith("name "):
            name = cmd.split(" ", 1)[1]
            self._set_vlan_name(name)
            return ""

        if cmd == "description":
            return ""

        if cmd.startswith("description "):
            desc = cmd.split(" ", 1)[1]
            self._set_description(desc)
            return ""

        if cmd == "undo description":
            self._set_description("")
            return ""

        if cmd == "shutdown":
            self._set_admin_up(False)
            return ""

        if cmd == "undo shutdown":
            self._set_admin_up(True)
            return ""

        if cmd.startswith("port link-type "):
            link_type = cmd.split()[-1]
            self._set_interface_field("link_type", link_type)
            return ""

        if cmd.startswith("port default vlan "):
            vlan_id = int(cmd.split()[-1])
            self._set_interface_field("access_vlan", vlan_id)
            return ""

        if cmd.startswith("port trunk allow-pass vlan "):
            vlan_str = cmd.split("vlan ", 1)[1]
            vlans = self._parse_vlan_list(vlan_str)
            self._set_interface_field("trunk_allowed_vlans", vlans)
            return ""

        if cmd == "return":
            self._context_stack.clear()
            self._current_vlan_id = None
            self._current_ifname = None
            return "Return to user view"

        if cmd == "save" or cmd == "save force":
            return "Warning: The current configuration will be written to the device. Are you sure? [Y/N]:y\nNow saving the current configuration to the slot 1.\nSave the configuration successfully."

        return ""

    def send_config_set(self, config_commands: list[str]) -> str:
        results: list[str] = []
        for cmd in config_commands:
            result = self.send_command(cmd)
            results.append(result)
        return "\n".join(results)

    def send_command_timing(self, command: str) -> str:
        return self.send_command(command)

    def save_config(self) -> str:
        return self.send_command("save force")

    def __enter__(self) -> MockSSHConnection:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()

    def _handle_display_version(self) -> str:
        s = self._simulated_state
        return (
            f"Huawei Versatile Routing Platform Software\n"
            f"VRP (R) Software, Version {s['firmware_version']}\n"
            f"Copyright (C) 2012-{2026} Huawei Technologies Co., Ltd.\n"
            f"HUAWEI S5720-28X-SI-AC uptime is 0 days, 0:00:00\n"
            f"Patch Version: none\n"
            f"{s['model']} version information\n"
            f"1. PCB    Version : CEM28X19A    VER A\n"
            f"2. MAB    Version : 1\n"
            f"3. Board  Type    : S5720-28X-SI-AC\n"
            f"4. CPLD1  Version : 102\n"
            f"5. BIOS   Version : 386\n"
            f"6. Bootstrap Version : 581\n"
            f"7. Board  Serial  Number : {s['serial_number']}\n"
            f"8. Manufacturing Version : V2\n"
            f"9. Hardware Version : VER A"
        )

    def _handle_display_vlan(self, cmd: str) -> str:
        vlan_id = None
        match = re.search(r"vlan\s+(\d+)", cmd)
        if match:
            vlan_id = int(match.group(1))

        if vlan_id is not None:
            vlan_data = self._simulated_vlans.get(vlan_id)
            if vlan_data is None:
                return f"Error: VLAN {vlan_id} does not exist."
            name = vlan_data.get("name", "")
            desc = vlan_data.get("description", "")
            result = f"VLAN ID: {vlan_id}\n"
            if name:
                result += f"  Name: {name}\n"
            if desc:
                result += f"  Description: {desc}\n"
            return result

        if not self._simulated_vlans:
            return "VID  Type     Ports\n1    common   UT:GE1/0/1(U)  GE1/0/2(U)  GE1/0/3(U)  GE1/0/4(U)\n                  GE1/0/5(U)  GE1/0/6(U)  GE1/0/7(U)  GE1/0/8(U)\n                  GE1/0/9(U)  GE1/0/10(U) GE1/0/11(U) GE1/0/12(U)\n                  GE1/0/13(U) GE1/0/14(U) GE1/0/15(U) GE1/0/16(U)\n                  GE1/0/17(U) GE1/0/18(U) GE1/0/19(U) GE1/0/20(U)\n                  GE1/0/21(U) GE1/0/22(U) GE1/0/23(U) GE1/0/24(U)\n                  XGE1/0/1(U) XGE1/0/2(U)"

        lines = ["VID  Type     Ports"]
        for vid, data in sorted(self._simulated_vlans.items()):
            name = data.get("name", "")
            lines.append(f"{vid:<5} common   (VLAN {vid})")
        return "\n".join(lines)

    def _handle_display_interface(self, cmd: str) -> str:
        ifname = cmd.split()[-1] if " " in cmd else ""
        if not ifname:
            return "Error: Interface name required."

        iface_data = self._simulated_interfaces.get(ifname, {})
        admin_up = iface_data.get("admin_up", True)
        link_type = iface_data.get("link_type", "access")
        access_vlan = iface_data.get("access_vlan")
        trunk_vlans = iface_data.get("trunk_allowed_vlans", [])
        desc = iface_data.get("description", "")

        result = (
            f"Interface {ifname} current state :\n"
            f"Link type:{link_type} line protocol is {'up' if admin_up else 'down'}\n"
            f"Current system time: 2026-07-24 00:00:00\n"
            f"Last 300 seconds input:  0 packets/sec  0 bytes/sec\n"
            f"Last 300 seconds output: 0 packets/sec  0 bytes/sec\n"
        )
        if desc:
            result += f"  Description: {desc}\n"
        if link_type == "access" and access_vlan:
            result += f"  Access VLAN: {access_vlan}\n"
        if link_type == "trunk" and trunk_vlans:
            result += f"  Trunk allowed VLANs: {','.join(map(str, trunk_vlans))}\n"
        return result

    def _handle_display_current_config(self) -> str:
        lines = [
            "!Software Version V200R023C00SPC600",
            "#",
            f"sysname {self._simulated_state['hostname']}",
            "#",
            "vlan batch",
        ]
        for vid in sorted(self._simulated_vlans.keys()):
            vlan_data = self._simulated_vlans[vid]
            lines.append(f" vlan {vid}")
            if vlan_data.get("name"):
                lines.append(f"  name {vlan_data['name']}")
            if vlan_data.get("description"):
                lines.append(f"  description {vlan_data['description']}")

        for ifname, iface_data in sorted(self._simulated_interfaces.items()):
            lines.append("#")
            lines.append(f"interface {ifname}")
            iface_desc = iface_data.get("description", "")
            if iface_desc:
                lines.append(f" description {iface_desc}")
            if not iface_data.get("admin_up", True):
                lines.append(" shutdown")
            link_type = iface_data.get("link_type", "access")
            lines.append(f" port link-type {link_type}")
            if link_type == "access" and iface_data.get("access_vlan"):
                lines.append(f" port default vlan {iface_data['access_vlan']}")
            if link_type == "trunk" and iface_data.get("trunk_allowed_vlans"):
                vlans_str = ",".join(map(str, iface_data["trunk_allowed_vlans"]))
                lines.append(f" port trunk allow-pass vlan {vlans_str}")

        lines.append("#")
        lines.append("return")
        return "\n".join(lines)

    def _handle_quit(self) -> None:
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

    def _handle_vlan_cmd(self, cmd: str) -> None:
        vlan_id = int(cmd.split()[1])
        self._simulated_vlans.setdefault(vlan_id, {})
        self._context_stack.append({"type": "vlan", "vlan_id": vlan_id})
        self._current_vlan_id = vlan_id
        self._current_ifname = None

    def _handle_interface_cmd(self, cmd: str) -> None:
        ifname = cmd.split()[1]
        self._simulated_interfaces.setdefault(ifname, {"admin_up": True})
        self._context_stack.append({"type": "interface", "ifname": ifname})
        self._current_ifname = ifname
        self._current_vlan_id = None

    def _set_vlan_name(self, name: str) -> None:
        if self._current_vlan_id is not None:
            vlan_data = self._simulated_vlans.get(self._current_vlan_id, {})
            vlan_data["name"] = name

    def _set_description(self, desc: str) -> None:
        if self._current_vlan_id is not None:
            vlan_data = self._simulated_vlans.get(self._current_vlan_id, {})
            vlan_data["description"] = desc
        elif self._current_ifname is not None:
            iface_data = self._simulated_interfaces.get(self._current_ifname, {})
            iface_data["description"] = desc

    def _set_admin_up(self, admin_up: bool) -> None:
        if self._current_ifname is not None:
            iface_data = self._simulated_interfaces.get(self._current_ifname, {})
            iface_data["admin_up"] = admin_up

    def _set_interface_field(self, field: str, value: Any) -> None:
        if self._current_ifname is not None:
            iface_data = self._simulated_interfaces.setdefault(self._current_ifname, {"admin_up": True})
            iface_data[field] = value

    @staticmethod
    def _parse_vlan_list(vlan_str: str) -> list[int]:
        vlans: list[int] = []
        for part in vlan_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                vlans.extend(range(int(start), int(end) + 1))
            elif part.isdigit():
                vlans.append(int(part))
        return vlans
