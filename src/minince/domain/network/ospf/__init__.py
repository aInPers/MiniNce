from __future__ import annotations

from minince.domain.network.ospf.models import (
    OspfAuthType,
    OspfInterfaceIntent,
    OspfNetworkIntent,
    OspfNetworkType,
    OspfOperation,
    OspfProcessIntent,
)
from minince.domain.network.ospf.state import (
    OspfAreaState,
    OspfDiff,
    OspfInterfaceState,
    OspfProcessState,
    compute_diff,
)
from minince.domain.network.ospf.validators import validate_ospf_intent

__all__ = [
    "OspfAreaState",
    "OspfAuthType",
    "OspfDiff",
    "OspfInterfaceIntent",
    "OspfInterfaceState",
    "OspfNetworkIntent",
    "OspfNetworkType",
    "OspfOperation",
    "OspfProcessIntent",
    "OspfProcessState",
    "compute_diff",
    "validate_ospf_intent",
]
