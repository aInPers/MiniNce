from __future__ import annotations

from typing import Any

from minince.domain.devices.network_device import NetworkDevice
from minince.shared.exceptions import DeviceConnectionError

_DRIVER_REGISTRY: dict[str, type[NetworkDevice]] = {}


def register_driver(vendor: str, driver_class: type[NetworkDevice]) -> None:
    _DRIVER_REGISTRY[vendor] = driver_class


def get_driver(vendor: str, **kwargs: Any) -> NetworkDevice:
    driver_class = _DRIVER_REGISTRY.get(vendor)
    if driver_class is None:
        raise DeviceConnectionError(
            f"No driver registered for vendor: {vendor}",
            details={"vendor": vendor, "available": list(_DRIVER_REGISTRY.keys())},
        )
    return driver_class(**kwargs)


def list_registered_drivers() -> list[str]:
    return list(_DRIVER_REGISTRY.keys())


def _ensure_drivers_loaded() -> None:
    if _DRIVER_REGISTRY:
        return
    from minince.infrastructure.drivers.huawei_vrp.huawei_device import HuaweiDevice
    register_driver("HUAWEI", HuaweiDevice)


_ensure_drivers_loaded()
