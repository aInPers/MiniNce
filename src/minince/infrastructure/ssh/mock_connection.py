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
        # OSPF 模拟状态：process_id -> {router_id, areas, silent_interfaces, interfaces}
        self._simulated_ospf: dict[int, dict[str, Any]] = {}
        self._current_ospf_pid: int | None = None
        self._current_ospf_area: str | None = None
        # 模拟邻居：process_id -> list[neighbor dict]
        self._simulated_ospf_peers: dict[int, list[dict[str, Any]]] = {}

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

        if cmd.startswith("display ospf brief"):
            return self._handle_display_ospf_brief(cmd)

        if cmd.startswith("display ospf peer"):
            return self._handle_display_ospf_peer(cmd)

        if cmd.startswith("display ospf interface"):
            return self._handle_display_ospf_interface(cmd)

        if cmd.startswith("display current-configuration configuration ospf"):
            return self._handle_display_ospf_config()

        if cmd.startswith("display current-configuration"):
            return self._handle_display_current_config()

        if cmd == "display this":
            return self._handle_display_this()

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

        if cmd.startswith("undo interface "):
            # 删除接口（如 undo interface Vlanif100 删除 VLANIF 接口）
            ifname = cmd.split(None, 2)[2].strip()
            if ifname in self._simulated_interfaces:
                del self._simulated_interfaces[ifname]
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

        # OSPF 接口视图命令（优先于进程级 undo ospf {pid} 匹配）
        if cmd.startswith("ospf enable ") and self._current_ifname is not None:
            self._set_ospf_interface_enable(cmd)
            return ""

        if cmd == "undo ospf enable" and self._current_ifname is not None:
            self._unset_ospf_interface_enable()
            return ""

        if cmd.startswith("ospf cost ") and self._current_ifname is not None:
            self._set_ospf_interface_cost(int(cmd.split()[-1]))
            return ""

        if cmd == "undo ospf cost" and self._current_ifname is not None:
            self._set_ospf_interface_cost(None)
            return ""

        if cmd.startswith("ospf network-type ") and self._current_ifname is not None:
            self._set_ospf_interface_network_type(cmd.split()[-1])
            return ""

        if cmd == "undo ospf network-type" and self._current_ifname is not None:
            self._set_ospf_interface_network_type(None)
            return ""

        if cmd.startswith("ospf authentication-mode") and self._current_ifname is not None:
            self._set_ospf_interface_auth(cmd)
            return ""

        if cmd == "undo ospf authentication-mode" and self._current_ifname is not None:
            self._unset_ospf_interface_auth()
            return ""

        # OSPF 进程视图命令
        if self._is_ospf_enter(cmd):
            self._handle_ospf_enter(cmd)
            return ""

        # undo ospf {pid} —— 仅匹配纯数字 pid，避免误匹配 undo ospf enable/cost 等
        m_undo_ospf = re.match(r"undo ospf\s+(\d+)\s*$", cmd)
        if m_undo_ospf:
            pid = int(m_undo_ospf.group(1))
            self._simulated_ospf.pop(pid, None)
            self._simulated_ospf_peers.pop(pid, None)
            return ""

        if cmd.startswith("router-id "):
            self._set_ospf_router_id(cmd.split(" ", 1)[1])
            return ""

        if cmd.startswith("area "):
            self._handle_ospf_area_enter(cmd)
            return ""

        if cmd.startswith("network ") and self._current_ospf_area is not None:
            parts = cmd.split()
            self._add_ospf_network(parts[1], parts[2])
            return ""

        if cmd.startswith("undo network ") and self._current_ospf_area is not None:
            parts = cmd.split()
            self._remove_ospf_network(parts[2], parts[3])
            return ""

        if cmd.startswith("silent-interface "):
            self._add_ospf_silent(cmd.split(" ", 1)[1])
            return ""

        if cmd.startswith("undo silent-interface "):
            self._remove_ospf_silent(cmd.split(" ", 1)[1])
            return ""

        # OSPF 接口视图命令
        if cmd.startswith("ospf enable ") and self._current_ifname is not None:
            self._set_ospf_interface_enable(cmd)
            return ""

        if cmd == "undo ospf enable" and self._current_ifname is not None:
            self._unset_ospf_interface_enable()
            return ""

        if cmd.startswith("ospf cost ") and self._current_ifname is not None:
            self._set_ospf_interface_cost(int(cmd.split()[-1]))
            return ""

        if cmd == "undo ospf cost" and self._current_ifname is not None:
            self._set_ospf_interface_cost(None)
            return ""

        if cmd.startswith("ospf network-type ") and self._current_ifname is not None:
            self._set_ospf_interface_network_type(cmd.split()[-1])
            return ""

        if cmd == "undo ospf network-type" and self._current_ifname is not None:
            self._set_ospf_interface_network_type(None)
            return ""

        if cmd.startswith("ospf authentication-mode") and self._current_ifname is not None:
            self._set_ospf_interface_auth(cmd)
            return ""

        if cmd == "undo ospf authentication-mode" and self._current_ifname is not None:
            self._unset_ospf_interface_auth()
            return ""

        if cmd == "return":
            self._context_stack.clear()
            self._current_vlan_id = None
            self._current_ifname = None
            self._current_ospf_pid = None
            self._current_ospf_area = None
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

    def _handle_display_this(self) -> str:
        """模拟 display this 命令，返回当前视图的配置段。"""
        if self._current_vlan_id is not None:
            vlan_data = self._simulated_vlans.get(self._current_vlan_id, {})
            lines = ["#", f"vlan {self._current_vlan_id}"]
            if vlan_data.get("name"):
                lines.append(f" name {vlan_data['name']}")
            if vlan_data.get("description"):
                lines.append(f" description {vlan_data['description']}")
            lines.append("#")
            return "\n".join(lines)
        if self._current_ifname is not None:
            iface_data = self._simulated_interfaces.get(self._current_ifname, {})
            lines = ["#", f"interface {self._current_ifname}"]
            if iface_data.get("description"):
                lines.append(f" description {iface_data['description']}")
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
            return "\n".join(lines)
        return ""

    def _handle_quit(self) -> None:
        if self._context_stack:
            ctx = self._context_stack.pop()
            if ctx["type"] == "vlan":
                self._current_vlan_id = None
            elif ctx["type"] == "interface":
                self._current_ifname = None
            elif ctx["type"] == "ospf":
                self._current_ospf_pid = None
                self._current_ospf_area = None
            elif ctx["type"] == "ospf_area":
                self._current_ospf_area = None
        if self._context_stack:
            parent = self._context_stack[-1]
            if parent["type"] == "vlan":
                self._current_vlan_id = parent.get("vlan_id")
            elif parent["type"] == "interface":
                self._current_ifname = parent.get("ifname")
            elif parent["type"] == "ospf":
                self._current_ospf_pid = parent.get("ospf_pid")

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

    # ------------------------------------------------------------------
    # OSPF 模拟
    # ------------------------------------------------------------------
    @staticmethod
    def _is_ospf_enter(cmd: str) -> bool:
        """判断是否为进入 OSPF 视图命令（ospf {pid} 或 ospf {pid} router-id {rid}）。"""
        if not cmd.startswith("ospf "):
            return False
        parts = cmd.split()
        # ospf {pid} 或 ospf {pid} router-id {rid}
        if len(parts) >= 2 and parts[1].isdigit():
            return True
        return False

    def _handle_ospf_enter(self, cmd: str) -> None:
        parts = cmd.split()
        pid = int(parts[1])
        proc = self._simulated_ospf.setdefault(
            pid,
            {
                "router_id": None,
                "areas": {},  # area_id -> {"networks": [(addr, wildcard)], "auth_type": "none"}
                "silent_interfaces": set(),
                "interfaces": {},  # ifname -> {area_id, cost, network_type, auth_type, auth_key_id}
            },
        )
        # ospf {pid} router-id {rid}
        if len(parts) >= 4 and parts[2] == "router-id":
            proc["router_id"] = parts[3]
        self._context_stack.append({"type": "ospf", "ospf_pid": pid})
        self._current_ospf_pid = pid
        self._current_ospf_area = None
        self._current_vlan_id = None
        self._current_ifname = None

    def _set_ospf_router_id(self, rid: str) -> None:
        if self._current_ospf_pid is not None:
            self._simulated_ospf[self._current_ospf_pid]["router_id"] = rid

    def _handle_ospf_area_enter(self, cmd: str) -> None:
        if self._current_ospf_pid is None:
            return
        area_id = cmd.split()[1]
        proc = self._simulated_ospf[self._current_ospf_pid]
        proc["areas"].setdefault(area_id, {"networks": [], "auth_type": "none"})
        self._context_stack.append({"type": "ospf_area", "area_id": area_id})
        self._current_ospf_area = area_id

    def _add_ospf_network(self, addr: str, wildcard: str) -> None:
        if self._current_ospf_pid is None or self._current_ospf_area is None:
            return
        area = self._simulated_ospf[self._current_ospf_pid]["areas"].get(
            self._current_ospf_area
        )
        if area is None:
            return
        nets = area["networks"]
        entry = (addr, wildcard)
        if entry not in nets:
            nets.append(entry)

    def _remove_ospf_network(self, addr: str, wildcard: str) -> None:
        if self._current_ospf_pid is None or self._current_ospf_area is None:
            return
        area = self._simulated_ospf[self._current_ospf_pid]["areas"].get(
            self._current_ospf_area
        )
        if area is None:
            return
        entry = (addr, wildcard)
        if entry in area["networks"]:
            area["networks"].remove(entry)

    def _add_ospf_silent(self, ifname: str) -> None:
        if self._current_ospf_pid is not None:
            self._simulated_ospf[self._current_ospf_pid]["silent_interfaces"].add(ifname)

    def _remove_ospf_silent(self, ifname: str) -> None:
        if self._current_ospf_pid is not None:
            self._simulated_ospf[self._current_ospf_pid]["silent_interfaces"].discard(ifname)

    def _set_ospf_interface_enable(self, cmd: str) -> None:
        if self._current_ifname is None:
            return
        # ospf enable {pid} area {aid} —— 命令本身携带 pid，无需依赖 ospf 视图上下文
        parts = cmd.split()
        pid = int(parts[2])
        area_id = parts[4]
        proc = self._simulated_ospf.setdefault(
            pid,
            {
                "router_id": None,
                "areas": {},
                "silent_interfaces": set(),
                "interfaces": {},
            },
        )
        iface = proc["interfaces"].setdefault(
            self._current_ifname,
            {
                "area_id": None,
                "cost": None,
                "network_type": None,
                "auth_type": "none",
                "auth_key_id": None,
            },
        )
        iface["area_id"] = area_id

    def _unset_ospf_interface_enable(self) -> None:
        if self._current_ifname is None:
            return
        for proc in self._simulated_ospf.values():
            if self._current_ifname in proc["interfaces"]:
                proc["interfaces"].pop(self._current_ifname, None)
                break

    def _set_ospf_interface_cost(self, cost: int | None) -> None:
        iface = self._current_ospf_interface()
        if iface is not None:
            iface["cost"] = cost

    def _set_ospf_interface_network_type(self, nt: str | None) -> None:
        iface = self._current_ospf_interface()
        if iface is not None:
            iface["network_type"] = nt.lower() if nt else None

    def _set_ospf_interface_auth(self, cmd: str) -> None:
        iface = self._current_ospf_interface()
        if iface is None:
            return
        parts = cmd.split()
        if "hmac-md5" in parts:
            iface["auth_type"] = "hmac_md5"
            try:
                kid_idx = parts.index("key-id")
                iface["auth_key_id"] = int(parts[kid_idx + 1])
            except (ValueError, IndexError):
                pass
        elif "simple" in parts:
            iface["auth_type"] = "simple"
        else:
            iface["auth_type"] = "none"

    def _unset_ospf_interface_auth(self) -> None:
        iface = self._current_ospf_interface()
        if iface is not None:
            iface["auth_type"] = "none"
            iface["auth_key_id"] = None

    def _current_ospf_interface(self) -> dict[str, Any] | None:
        if self._current_ifname is None:
            return None
        for proc in self._simulated_ospf.values():
            if self._current_ifname in proc["interfaces"]:
                return proc["interfaces"][self._current_ifname]
        return None

    # ------------------------------------------------------------------
    # OSPF display 处理
    # ------------------------------------------------------------------
    def _handle_display_ospf_brief(self, cmd: str) -> str:
        # display ospf brief [process {pid}]
        pid = None
        m = re.search(r"process\s+(\d+)", cmd)
        if m:
            pid = int(m.group(1))
        if pid is not None:
            proc = self._simulated_ospf.get(pid)
            if proc is None:
                return f"Error: OSPF Process {pid} not found."
            rid = proc["router_id"] or "0.0.0.0"
            return (
                f"OSPF Process {pid} with Router ID {rid}\n"
                f"OSPF Protocol is enabled\n"
                f"Area: 0.0.0.0\n"
            )
        # 无 pid 时列出所有进程
        if not self._simulated_ospf:
            return "OSPF Process is not enabled."
        lines = []
        for p, proc in sorted(self._simulated_ospf.items()):
            rid = proc["router_id"] or "0.0.0.0"
            lines.append(f"OSPF Process {p} with Router ID {rid}")
            lines.append("OSPF Protocol is enabled")
        return "\n".join(lines)

    def _handle_display_ospf_peer(self, cmd: str) -> str:
        pid = None
        m = re.search(r"process\s+(\d+)", cmd)
        if m:
            pid = int(m.group(1))
        pids = [pid] if pid is not None else sorted(self._simulated_ospf.keys())
        if not pids:
            return "OSPF Process is not enabled."
        lines: list[str] = []
        for p in pids:
            proc = self._simulated_ospf.get(p)
            if proc is None:
                continue
            rid = proc["router_id"] or "0.0.0.0"
            lines.append(f"OSPF Process {p} with Router ID {rid}")
            lines.append("Area 0.0.0.0 neighbors")
            lines.append("RouterID       Address         State        Interface")
            peers = self._simulated_ospf_peers.get(p, [])
            for peer in peers:
                lines.append(
                    f"{peer['neighbor_id']:<15}{peer['address']:<17}{peer['state']:<13}{peer['interface']}"
                )
        return "\n".join(lines)

    def _handle_display_ospf_interface(self, cmd: str) -> str:
        pid = None
        m = re.search(r"process\s+(\d+)", cmd)
        if m:
            pid = int(m.group(1))
        pids = [pid] if pid is not None else sorted(self._simulated_ospf.keys())
        if not pids:
            return "OSPF Process is not enabled."
        lines: list[str] = []
        for p in pids:
            proc = self._simulated_ospf.get(p)
            if proc is None:
                continue
            for ifname, idata in sorted(proc["interfaces"].items()):
                area = idata.get("area_id") or "0.0.0.0"
                cost = idata.get("cost")
                nt = idata.get("network_type") or "broadcast"
                cost_str = str(cost) if cost is not None else "-"
                lines.append(
                    f"{ifname} is up\n"
                    f" Area {area}\n"
                    f" Cost {cost_str}\n"
                    f" Network Type {nt}\n"
                )
        return "\n".join(lines)

    def _handle_display_ospf_config(self) -> str:
        if not self._simulated_ospf:
            return "#\nreturn"
        lines: list[str] = ["!Software Version V200R023C00SPC600", "#"]
        for pid, proc in sorted(self._simulated_ospf.items()):
            rid = proc["router_id"]
            if rid:
                lines.append(f"ospf {pid} router-id {rid}")
            else:
                lines.append(f"ospf {pid}")
            for area_id, area in sorted(proc["areas"].items()):
                lines.append(f" area {area_id}")
                for addr, wildcard in area["networks"]:
                    lines.append(f"  network {addr} {wildcard}")
                if area.get("auth_type") and area["auth_type"] != "none":
                    lines.append(f"  authentication-mode {area['auth_type']}")
            for ifname in sorted(proc["silent_interfaces"]):
                lines.append(f" silent-interface {ifname}")
            lines.append("#")
        for pid, proc in sorted(self._simulated_ospf.items()):
            for ifname, idata in sorted(proc["interfaces"].items()):
                lines.append(f"interface {ifname}")
                if idata.get("area_id"):
                    lines.append(f" ospf enable {pid} area {idata['area_id']}")
                if idata.get("cost") is not None:
                    lines.append(f" ospf cost {idata['cost']}")
                if idata.get("network_type"):
                    lines.append(f" ospf network-type {idata['network_type']}")
                if idata.get("auth_type") == "hmac_md5":
                    kid = idata.get("auth_key_id", 1)
                    lines.append(
                        f" ospf authentication-mode hmac-md5 key-id {kid} cipher %^%#xx%^%#"
                    )
                elif idata.get("auth_type") == "simple":
                    lines.append(" ospf authentication-mode simple cipher %^%#xx%^%#")
                lines.append("#")
        lines.append("return")
        return "\n".join(lines)

    def add_ospf_peer(self, process_id: int, neighbor_id: str, address: str,
                      state: str = "Full", interface: str = "GigabitEthernet0/0/1") -> None:
        """测试辅助：为模拟设备注入一个 OSPF 邻居。"""
        self._simulated_ospf_peers.setdefault(process_id, []).append(
            {
                "neighbor_id": neighbor_id,
                "address": address,
                "state": state,
                "interface": interface,
            }
        )
