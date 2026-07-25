from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from minince.domain.network.ospf.models import (
    OspfAuthType,
    OspfInterfaceIntent,
    OspfNetworkIntent,
    OspfNetworkType,
    OspfOperation,
    OspfProcessIntent,
)


class TestOspfNetworkIntent:
    def test_area_id_accepts_int(self) -> None:
        net = OspfNetworkIntent(network="10.0.0.0/24", area_id=0)
        assert str(net.area_id) == "0.0.0.0"

    def test_area_id_accepts_dotted(self) -> None:
        net = OspfNetworkIntent(network="10.0.0.0/24", area_id="0.0.0.1")
        assert str(net.area_id) == "0.0.0.1"

    def test_area_id_rejects_out_of_range(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfNetworkIntent(network="10.0.0.0/24", area_id=2**32)

    def test_network_strict_false_normalizes_host_bits(self) -> None:
        net = OspfNetworkIntent(network="10.0.0.5/24", area_id=0)
        assert str(net.network) == "10.0.0.0/24"

    def test_network_with_wildcard(self) -> None:
        net = OspfNetworkIntent(network="10.0.0.0/24", area_id=0)
        assert net.network_with_wildcard() == "10.0.0.0 0.0.0.255"


class TestOspfInterfaceIntent:
    def test_hmac_md5_requires_key_id_and_secret(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(
                interface_name="GigabitEthernet0/0/1",
                area_id=0,
                auth_type=OspfAuthType.HMAC_MD5,
            )

    def test_hmac_md5_requires_secret(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(
                interface_name="GigabitEthernet0/0/1",
                area_id=0,
                auth_type=OspfAuthType.HMAC_MD5,
                auth_key_id=1,
            )

    def test_simple_requires_secret(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(
                interface_name="GigabitEthernet0/0/1",
                area_id=0,
                auth_type=OspfAuthType.SIMPLE,
            )

    def test_none_rejects_secret(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(
                interface_name="GigabitEthernet0/0/1",
                area_id=0,
                auth_type=OspfAuthType.NONE,
                auth_secret="leak",
            )

    def test_interface_name_rejects_injection(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(
                interface_name="GE0/0/1\nquit",
                area_id=0,
            )

    def test_interface_name_rejects_separator(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfInterfaceIntent(interface_name="GE0/0/1;undo ospf", area_id=0)

    def test_auth_summary_has_no_secret(self) -> None:
        iface = OspfInterfaceIntent(
            interface_name="GigabitEthernet0/0/1",
            area_id=0,
            auth_type=OspfAuthType.HMAC_MD5,
            auth_key_id=1,
            auth_secret="supersecret",
        )
        summary = iface.auth_summary()
        assert summary == {
            "auth_type": "hmac_md5",
            "auth_key_id": 1,
            "auth_secret_configured": True,
        }
        assert "supersecret" not in str(summary)

    def test_secret_not_in_repr(self) -> None:
        iface = OspfInterfaceIntent(
            interface_name="GigabitEthernet0/0/1",
            area_id=0,
            auth_type=OspfAuthType.SIMPLE,
            auth_secret="supersecret",
        )
        assert "supersecret" not in repr(iface)


class TestOspfProcessIntent:
    def test_reject_duplicate_interfaces(self) -> None:
        with pytest.raises(PydanticValidationError):
            OspfProcessIntent(
                process_id=1,
                interfaces=[
                    OspfInterfaceIntent(interface_name="GigabitEthernet0/0/1", area_id=0),
                    OspfInterfaceIntent(interface_name="gigabitethernet0/0/1", area_id=0),
                ],
            )

    def test_to_structured_intent_has_no_plaintext_secret(self) -> None:
        intent = OspfProcessIntent(
            process_id=1,
            router_id="10.255.0.1",
            networks=[OspfNetworkIntent(network="10.10.10.0/24", area_id=0)],
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1",
                    area_id=0,
                    auth_type=OspfAuthType.HMAC_MD5,
                    auth_key_id=1,
                    auth_secret="supersecret",
                )
            ],
        )
        structured = intent.to_structured_intent(auth_secret_encrypted="ENC_TOKEN")
        blob = repr(structured)
        assert "supersecret" not in blob
        assert "ENC_TOKEN" in blob  # 密文存在
        assert structured["feature"] == "OSPF"
        assert structured["interfaces"][0]["auth_secret_configured"] is True
        assert structured["interfaces"][0]["auth_secret_encrypted"] == "ENC_TOKEN"

    def test_safe_repr_has_no_secret(self) -> None:
        intent = OspfProcessIntent(
            process_id=1,
            interfaces=[
                OspfInterfaceIntent(
                    interface_name="GigabitEthernet0/0/1",
                    area_id=0,
                    auth_type=OspfAuthType.SIMPLE,
                    auth_secret="supersecret",
                )
            ],
        )
        assert "supersecret" not in intent.safe_repr()

    def test_default_operation_is_ensure_present(self) -> None:
        intent = OspfProcessIntent(process_id=1)
        assert intent.operation == OspfOperation.ENSURE_PRESENT
