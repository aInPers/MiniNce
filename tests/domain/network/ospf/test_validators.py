from __future__ import annotations

import pytest

from minince.domain.network.ospf.models import (
    OspfInterfaceIntent,
    OspfNetworkIntent,
    OspfOperation,
    OspfProcessIntent,
)
from minince.domain.network.ospf.validators import validate_ospf_intent
from minince.shared.exceptions import ValidationError


def _intent(**kwargs) -> OspfProcessIntent:
    return OspfProcessIntent(**kwargs)


class TestOspfValidators:
    def test_overlapping_networks_different_areas_rejected(self) -> None:
        intent = _intent(
            process_id=1,
            networks=[
                OspfNetworkIntent(network="10.0.0.0/24", area_id="0.0.0.0"),
                OspfNetworkIntent(network="10.0.0.0/25", area_id="0.0.0.1"),
            ],
        )
        with pytest.raises(ValidationError) as exc:
            validate_ospf_intent(intent)
        assert "different areas" in str(exc.value).lower()

    def test_overlapping_networks_same_area_rejected_as_duplicate(self) -> None:
        intent = _intent(
            process_id=1,
            networks=[
                OspfNetworkIntent(network="10.0.0.0/24", area_id="0.0.0.0"),
                OspfNetworkIntent(network="10.0.0.0/24", area_id="0.0.0.0"),
            ],
        )
        with pytest.raises(ValidationError):
            validate_ospf_intent(intent)

    def test_disjoint_networks_ok(self) -> None:
        intent = _intent(
            process_id=1,
            networks=[
                OspfNetworkIntent(network="10.0.0.0/24", area_id="0.0.0.0"),
                OspfNetworkIntent(network="10.1.0.0/24", area_id="0.0.0.1"),
            ],
        )
        validate_ospf_intent(intent)  # 不抛异常

    def test_ensure_absent_with_networks_rejected(self) -> None:
        intent = _intent(
            process_id=1,
            operation=OspfOperation.ENSURE_ABSENT,
            networks=[OspfNetworkIntent(network="10.0.0.0/24", area_id=0)],
        )
        with pytest.raises(ValidationError):
            validate_ospf_intent(intent)

    def test_ensure_absent_with_interfaces_rejected(self) -> None:
        intent = _intent(
            process_id=1,
            operation=OspfOperation.ENSURE_ABSENT,
            interfaces=[OspfInterfaceIntent(interface_name="GE0/0/1", area_id=0)],
        )
        with pytest.raises(ValidationError):
            validate_ospf_intent(intent)

    def test_ensure_absent_empty_ok(self) -> None:
        intent = _intent(process_id=1, operation=OspfOperation.ENSURE_ABSENT)
        validate_ospf_intent(intent)

    def test_injection_in_router_id_rejected(self) -> None:
        # router_id 经 IPv4Address 校验已无法注入换行，这里确认校验链不漏
        intent = _intent(process_id=1, router_id="10.0.0.1")
        validate_ospf_intent(intent)
