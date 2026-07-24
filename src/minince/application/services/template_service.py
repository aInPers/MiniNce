from __future__ import annotations

from typing import Any

from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.template_repository import TemplateRepository
from minince.shared.exceptions import TemplateNotFoundError, ValidationError


class TemplateService:
    def __init__(
        self,
        template_repo: TemplateRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        self._template_repo = template_repo
        self._audit_repo = audit_repo

    def create_template(
        self,
        name: str,
        vendor: str,
        feature: str,
        template_content: str,
        version: str = "1.0",
        variable_schema: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Any:
        existing = self._template_repo.get_by_name_and_vendor(name, vendor)
        if existing:
            raise ValidationError(
                f"Template with name '{name}' for vendor '{vendor}' already exists"
            )

        template = self._template_repo.create(
            name=name,
            vendor=vendor,
            feature=feature,
            template_content=template_content,
            version=version,
            variable_schema=variable_schema,
            enabled=enabled,
        )

        self._audit_repo.log(
            action="CREATE",
            resource_type="TEMPLATE",
            resource_id=str(template.id),
            actor="web",
            details={"name": name, "vendor": vendor, "feature": feature},
        )

        return template

    def update_template(
        self,
        template_id: int,
        **kwargs: Any,
    ) -> Any:
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError(template_id)

        updated = self._template_repo.update(template_id, **kwargs)

        self._audit_repo.log(
            action="UPDATE",
            resource_type="TEMPLATE",
            resource_id=str(template_id),
            actor="web",
            details={"changed_fields": [k for k, v in kwargs.items() if v is not None]},
        )

        return updated

    def delete_template(self, template_id: int) -> bool:
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError(template_id)

        result = self._template_repo.delete_by_id(template_id)

        self._audit_repo.log(
            action="DELETE",
            resource_type="TEMPLATE",
            resource_id=str(template_id),
            actor="web",
            details={"name": template.name},
        )

        return result

    def get_template(self, template_id: int) -> Any:
        template = self._template_repo.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError(template_id)
        return template

    def list_templates(
        self,
        skip: int = 0,
        limit: int = 100,
        vendor: str | None = None,
        feature: str | None = None,
    ) -> tuple[list[Any], int]:
        templates = self._template_repo.get_all(
            skip=skip, limit=limit, vendor=vendor, feature=feature
        )
        total = self._template_repo.count_all(vendor=vendor, feature=feature)
        return templates, total
