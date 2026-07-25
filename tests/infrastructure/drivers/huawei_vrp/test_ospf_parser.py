from __future__ import annotations

from minince.domain.network.ospf.state import OspfProcessState
from minince.infrastructure.drivers.huawei_vrp.ospf_parser import HuaweiOspfParser


BRIEF_RUNNING = """OSPF Process 1 with Router ID 10.255.0.1
OSPF Protocol is enabled
Area: 0.0.0.0
"""

BRIEF_DISABLED = """OSPF Process 1 with Router ID 10.255.0.1
OSPF Protocol is disabled
"""

RUNNING_CONFIG = """!Software Version V200R023C00SPC600
#
ospf 1 router-id 10.255.0.1
 area 0.0.0.0
  network 10.10.10.0 0.0.0.255
  network 10.20.20.0 0.0.0.255
  silent-interface GigabitEthernet0/0/2
#
interface GigabitEthernet0/0/1
 ospf enable 1 area 0.0.0.0
 ospf cost 10
 ospf network-type p2p
#
interface GigabitEthernet0/0/2
 ospf enable 1 area 0.0.0.0
#
interface GigabitEthernet0/0/3
 ospf enable 1 area 0.0.0.0
 ospf authentication-mode hmac-md5 key-id 1 cipher %^%#xx%^%#
#
return
"""

PEER_OUTPUT = """OSPF Process 1 with Router ID 10.255.0.1
Area 0.0.0.0 neighbors
RouterID       Address         State        Interface
10.0.0.2       10.10.10.2      Full         GigabitEthernet0/0/1
10.0.0.3       10.10.10.3      ExStart      GigabitEthernet0/0/1
"""


class TestOspfParserBrief:
    def setup_method(self) -> None:
        self.parser = HuaweiOspfParser()

    def test_running_with_router_id(self) -> None:
        running, rid = self.parser.parse_brief(BRIEF_RUNNING, 1)
        assert running is True
        assert rid == "10.255.0.1"

    def test_disabled_not_running(self) -> None:
        running, _ = self.parser.parse_brief(BRIEF_DISABLED, 1)
        assert running is False

    def test_empty_output(self) -> None:
        running, rid = self.parser.parse_brief("", 1)
        assert running is False
        assert rid is None


class TestOspfParserRunningConfig:
    def setup_method(self) -> None:
        self.parser = HuaweiOspfParser()

    def test_parses_router_id(self) -> None:
        state = self.parser.parse_running_config(RUNNING_CONFIG, 1)
        assert state.router_id == "10.255.0.1"

    def test_parses_networks_by_area(self) -> None:
        state = self.parser.parse_running_config(RUNNING_CONFIG, 1)
        area = state.areas["0.0.0.0"]
        assert "10.10.10.0/24" in area.networks
        assert "10.20.20.0/24" in area.networks

    def test_parses_silent_interface(self) -> None:
        state = self.parser.parse_running_config(RUNNING_CONFIG, 1)
        assert "GigabitEthernet0/0/2" in state.silent_interfaces

    def test_parses_interface_enable_cost_type(self) -> None:
        state = self.parser.parse_running_config(RUNNING_CONFIG, 1)
        iface = state.interfaces["GigabitEthernet0/0/1"]
        assert iface.area_id == "0.0.0.0"
        assert iface.cost == 10
        assert iface.network_type == "p2p"

    def test_parses_hmac_md5_auth(self) -> None:
        state = self.parser.parse_running_config(RUNNING_CONFIG, 1)
        iface = state.interfaces["GigabitEthernet0/0/3"]
        assert iface.auth_type == "hmac_md5"
        assert iface.auth_key_id == 1

    def test_missing_process_returns_not_running(self) -> None:
        state = self.parser.parse_running_config("nothing here", 1)
        assert state.running is False

    def test_empty_output(self) -> None:
        state = self.parser.parse_running_config("", 1)
        assert state.running is False


class TestOspfParserPeer:
    def setup_method(self) -> None:
        self.parser = HuaweiOspfParser()

    def test_parses_neighbors(self) -> None:
        peers = self.parser.parse_peer(PEER_OUTPUT)
        assert len(peers) == 2
        full_peers = [p for p in peers if p["is_full"]]
        assert len(full_peers) == 1
        assert full_peers[0]["neighbor_id"] == "10.0.0.2"

    def test_empty_peer_output(self) -> None:
        assert self.parser.parse_peer("") == []


class TestOspfParserWildcard:
    def test_wildcard_to_cidr(self) -> None:
        p = HuaweiOspfParser()
        assert p._wildcard_to_cidr("10.10.10.0", "0.0.0.255") == "10.10.10.0/24"
        assert p._wildcard_to_cidr("10.0.0.0", "0.255.255.255") == "10.0.0.0/8"
        assert p._wildcard_to_cidr("192.168.1.0", "0.0.0.3") == "192.168.1.0/30"
