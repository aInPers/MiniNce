from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VlanIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["create", "update", "delete"]
    vlan_id: int = Field(..., ge=1, le=4094)
    name: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v: int) -> int:
        if v < 1 or v > 4094:
            raise ValueError(f"VLAN ID must be between 1 and 4094, got {v}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("VLAN name cannot be empty")
            if len(v) > 32:
                raise ValueError("VLAN name must be at most 32 characters")
        return v


class InterfaceIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface_name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    admin_up: bool | None = None
    link_type: Literal["access", "trunk", "hybrid"] | None = None
    access_vlan: int | None = Field(default=None, ge=1, le=4094)
    trunk_allowed_vlans: list[int] | None = None

    @field_validator("interface_name")
    @classmethod
    def validate_interface_name(cls, v: str) -> str:
        import re

        if not re.match(r"^[A-Za-z0-9_\-/\.]+$", v):
            raise ValueError(f"Invalid interface name: {v}")
        return v

    @field_validator("access_vlan")
    @classmethod
    def validate_access_vlan(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 4094):
            raise ValueError(f"Access VLAN must be between 1 and 4094, got {v}")
        return v

    @field_validator("trunk_allowed_vlans")
    @classmethod
    def validate_trunk_vlans(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            for vid in v:
                if vid < 1 or vid > 4094:
                    raise ValueError(f"Trunk VLAN ID must be between 1 and 4094, got {vid}")
        return v

    def validate_cross_fields(self) -> None:
        if self.link_type == "access" and self.trunk_allowed_vlans:
            raise ValueError("Access interface cannot have trunk allowed VLANs")
        if self.link_type == "trunk" and self.access_vlan is not None:
            raise ValueError("Trunk interface cannot have access VLAN")
