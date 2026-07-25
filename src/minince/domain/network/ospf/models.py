from __future__ import annotations

import json
from enum import StrEnum
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OspfOperation(StrEnum):
    ENSURE_PRESENT = "ensure_present"
    ENSURE_ABSENT = "ensure_absent"


class OspfNetworkType(StrEnum):
    BROADCAST = "broadcast"
    P2P = "p2p"
    NBMA = "nbma"
    P2MP = "p2mp"


class OspfAuthType(StrEnum):
    NONE = "none"
    SIMPLE = "simple"
    HMAC_MD5 = "hmac_md5"


def _area_id_to_dotted(value: Any) -> str:
    """将 Area ID 归一化为点分十进制字符串（设备无关）。

    接受 int（0~4294967295，0 等价于 0.0.0.0）或点分十进制字符串。
    """
    if isinstance(value, bool):
        raise ValueError("Area ID must not be a boolean")
    if isinstance(value, int):
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError(f"Area ID out of range: {value}")
        return str(IPv4Address(value))
    if isinstance(value, str):
        text = value.strip()
        # 纯数字字符串也按整数处理
        if text.isdigit():
            return _area_id_to_dotted(int(text))
        return str(IPv4Address(text))
    raise ValueError(f"Invalid Area ID: {value!r}")


class OspfNetworkIntent(BaseModel):
    """设备无关的 OSPF 网段发布意图。"""

    model_config = ConfigDict(extra="forbid")

    network: IPv4Network
    area_id: IPv4Address

    @field_validator("area_id", mode="before")
    @classmethod
    def _normalize_area_id(cls, v: Any) -> Any:
        return _area_id_to_dotted(v)

    @field_validator("network", mode="before")
    @classmethod
    def _normalize_network(cls, v: Any) -> Any:
        # IPv4Network 默认会严格校验主机位，这里允许主机位非零并自动取网络地址
        if isinstance(v, str):
            return IPv4Network(v, strict=False)
        return v

    def network_with_wildcard(self) -> str:
        """返回 'network wildcard' 形式（华为 VRP network 命令所需）。"""
        return f"{self.network.network_address} {IPv4Address(int(self.network.netmask) ^ 0xFFFFFFFF)}"


class OspfInterfaceIntent(BaseModel):
    """设备无关的 OSPF 接口意图。"""

    model_config = ConfigDict(extra="forbid")

    interface_name: str = Field(..., min_length=1, max_length=64)
    area_id: IPv4Address
    cost: int | None = Field(default=None, ge=1, le=65535)
    network_type: OspfNetworkType | None = None
    silent: bool = False
    auth_type: OspfAuthType = OspfAuthType.NONE
    auth_key_id: int | None = Field(default=None, ge=1, le=255)
    # 明文密码仅在输入校验阶段存在；落库前会被加密脱敏。
    auth_secret: str | None = Field(default=None, min_length=1, max_length=255, repr=False)

    @field_validator("area_id", mode="before")
    @classmethod
    def _normalize_area_id(cls, v: Any) -> Any:
        return _area_id_to_dotted(v)

    @field_validator("interface_name")
    @classmethod
    def _validate_interface_name(cls, v: str) -> str:
        import re

        if not re.match(r"^[A-Za-z0-9_\-/\.]+$", v):
            raise ValueError(f"Invalid interface name: {v}")
        # 禁止换行符与命令分隔符注入
        if any(ch in v for ch in ("\n", "\r", ";", "|")):
            raise ValueError(f"Interface name contains illegal characters: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_auth_params(self) -> OspfInterfaceIntent:
        if self.auth_type == OspfAuthType.HMAC_MD5:
            if self.auth_key_id is None:
                raise ValueError("hmac_md5 authentication requires auth_key_id")
            if not self.auth_secret:
                raise ValueError("hmac_md5 authentication requires auth_secret")
        elif self.auth_type == OspfAuthType.SIMPLE:
            if not self.auth_secret:
                raise ValueError("simple authentication requires auth_secret")
        else:  # NONE
            if self.auth_key_id is not None or self.auth_secret:
                raise ValueError("auth_key_id/auth_secret must not be set when auth_type is none")
        return self

    def auth_summary(self) -> dict[str, Any]:
        """返回不含明文密码的认证摘要，用于日志/审计/任务记录。"""
        return {
            "auth_type": self.auth_type.value,
            "auth_key_id": self.auth_key_id,
            "auth_secret_configured": bool(self.auth_secret),
        }


class OspfProcessIntent(BaseModel):
    """设备无关的 OSPF 进程意图。"""

    model_config = ConfigDict(extra="forbid")

    operation: OspfOperation = OspfOperation.ENSURE_PRESENT
    process_id: int = Field(..., ge=1, le=65535)
    router_id: IPv4Address | None = None
    networks: list[OspfNetworkIntent] = Field(default_factory=list)
    interfaces: list[OspfInterfaceIntent] = Field(default_factory=list)

    @field_validator("interfaces")
    @classmethod
    def reject_duplicate_interfaces(
        cls,
        interfaces: list[OspfInterfaceIntent],
    ) -> list[OspfInterfaceIntent]:
        names = [item.interface_name.casefold() for item in interfaces]
        if len(names) != len(set(names)):
            raise ValueError("OSPF interface names must be unique")
        return interfaces

    def to_structured_intent(self, *, auth_secret_encrypted: str | None = None) -> dict[str, Any]:
        """转换为可落库的 structured_intent。

        - 不包含明文密码；认证密码以加密密文形式附带（由调用方加密）。
        - 每个接口仅保留认证摘要，避免明文密码进入任务记录。
        """
        return {
            "feature": "OSPF",
            "operation": self.operation.value,
            "process_id": self.process_id,
            "router_id": str(self.router_id) if self.router_id else None,
            "networks": [
                {
                    "network": str(n.network),
                    "area_id": str(n.area_id),
                }
                for n in self.networks
            ],
            "interfaces": [
                {
                    "interface_name": i.interface_name,
                    "area_id": str(i.area_id),
                    "cost": i.cost,
                    "network_type": i.network_type.value if i.network_type else None,
                    "silent": i.silent,
                    **i.auth_summary(),
                    # 加密密文随结构化意图落库，执行时解密；无密码则为 None
                    "auth_secret_encrypted": (
                        auth_secret_encrypted if i.auth_secret else None
                    ),
                }
                for i in self.interfaces
            ],
        }

    def safe_repr(self) -> str:
        """用于日志的脱敏表示。"""
        return json.dumps(
            {
                "operation": self.operation.value,
                "process_id": self.process_id,
                "router_id": str(self.router_id) if self.router_id else None,
                "networks": len(self.networks),
                "interfaces": [
                    {"interface_name": i.interface_name, **i.auth_summary()}
                    for i in self.interfaces
                ],
            },
            ensure_ascii=False,
        )
