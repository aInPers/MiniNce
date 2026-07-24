from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from minince.infrastructure.database.models import ConfigTemplate
from minince.infrastructure.repositories.base import BaseRepository


class TemplateRepository(BaseRepository):
    def get_by_id(self, template_id: int) -> ConfigTemplate | None:
        stmt = select(ConfigTemplate).where(ConfigTemplate.id == template_id)
        return self.scalar_one(stmt)

    def get_by_name_and_vendor(
        self, name: str, vendor: str
    ) -> ConfigTemplate | None:
        stmt = select(ConfigTemplate).where(
            ConfigTemplate.name == name,
            ConfigTemplate.vendor == vendor,
        )
        return self.scalar_one(stmt)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        vendor: str | None = None,
        feature: str | None = None,
        enabled: bool | None = None,
    ) -> list[ConfigTemplate]:
        stmt = select(ConfigTemplate)
        if vendor:
            stmt = stmt.where(ConfigTemplate.vendor == vendor)
        if feature:
            stmt = stmt.where(ConfigTemplate.feature == feature)
        if enabled is not None:
            stmt = stmt.where(ConfigTemplate.enabled == enabled)
        stmt = stmt.order_by(ConfigTemplate.created_at.desc()).offset(skip).limit(limit)
        return self.scalars(stmt)

    def count_all(
        self,
        vendor: str | None = None,
        feature: str | None = None,
        enabled: bool | None = None,
    ) -> int:
        stmt = select(ConfigTemplate)
        if vendor:
            stmt = stmt.where(ConfigTemplate.vendor == vendor)
        if feature:
            stmt = stmt.where(ConfigTemplate.feature == feature)
        if enabled is not None:
            stmt = stmt.where(ConfigTemplate.enabled == enabled)
        return self.count(stmt)

    def create(
        self,
        name: str,
        vendor: str,
        feature: str,
        template_content: str,
        version: str = "1.0",
        variable_schema: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ConfigTemplate:
        template = ConfigTemplate(
            name=name,
            vendor=vendor,
            feature=feature,
            version=version,
            template_content=template_content,
            variable_schema=variable_schema,
            enabled=enabled,
        )
        self.add(template)
        self.commit()
        self.refresh(template)
        return template

    def update(self, template_id: int, **kwargs: Any) -> ConfigTemplate | None:
        template = self.get_by_id(template_id)
        if template is None:
            return None

        for key, value in kwargs.items():
            if hasattr(template, key) and value is not None:
                setattr(template, key, value)

        template.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(template)
        return template

    def delete_by_id(self, template_id: int) -> bool:
        template = self.get_by_id(template_id)
        if template is None:
            return False

        self.delete(template)
        self.commit()
        return True

    def set_enabled(self, template_id: int, enabled: bool) -> ConfigTemplate | None:
        return self.update(template_id, enabled=enabled)
