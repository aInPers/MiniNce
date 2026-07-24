from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VlanTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(..., pattern="^(create|update|delete)$")
    vlan_id: int = Field(..., ge=1, le=4094)
    name: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=255)
    device_id: int = Field(..., ge=1)
    created_by: str = Field(default="web", max_length=100)


class InterfaceTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface_name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    admin_up: bool | None = None
    link_type: str | None = Field(default=None, pattern="^(access|trunk|hybrid)$")
    access_vlan: int | None = Field(default=None, ge=1, le=4094)
    trunk_allowed_vlans: list[int] | None = None
    device_id: int = Field(..., ge=1)
    created_by: str = Field(default="web", max_length=100)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_number: str
    task_type: str
    device_id: int
    status: str
    risk_level: str
    original_request: dict[str, Any] | None = None
    structured_intent: dict[str, Any] | None = None
    generated_commands: list[str] | None = None
    execution_output: dict[str, Any] | None = None
    verification_output: dict[str, Any] | None = None
    error_message: str | None = None
    created_by: str
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


class TaskStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    step_name: str
    status: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class TaskExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = Field(default=False)
