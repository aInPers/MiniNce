from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    vendor: str = Field(..., min_length=1, max_length=50)
    feature: str = Field(..., min_length=1, max_length=100)
    version: str = Field(default="1.0", max_length=50)
    template_content: str = Field(..., min_length=1)
    variable_schema: dict[str, Any] | None = None
    enabled: bool = True


class TemplateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    vendor: str | None = Field(default=None, min_length=1, max_length=50)
    feature: str | None = Field(default=None, min_length=1, max_length=100)
    version: str | None = Field(default=None, max_length=50)
    template_content: str | None = Field(default=None, min_length=1)
    variable_schema: dict[str, Any] | None = None
    enabled: bool | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    vendor: str
    feature: str
    version: str
    template_content: str
    variable_schema: dict[str, Any] | None = None
    enabled: bool
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    total: int
    items: list[TemplateResponse]
