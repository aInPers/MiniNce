from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    hostname: str = Field(..., min_length=1, max_length=255)
    management_ip: str = Field(..., min_length=1, max_length=45)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    vendor: str = Field(..., min_length=1, max_length=50)
    platform: str | None = None
    connection_type: str = Field(default="SSH", max_length=50)
    description: str | None = None


class DeviceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    management_ip: str | None = Field(default=None, min_length=1, max_length=45)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=255)
    vendor: str | None = Field(default=None, min_length=1, max_length=50)
    platform: str | None = None
    connection_type: str | None = Field(default=None, max_length=50)
    description: str | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hostname: str
    management_ip: str
    port: int
    username: str
    vendor: str
    platform: str | None = None
    connection_type: str
    status: str
    last_connected_at: str | None = None
    description: str | None = None
    created_at: str
    updated_at: str


class DeviceListResponse(BaseModel):
    total: int
    items: list[DeviceResponse]
