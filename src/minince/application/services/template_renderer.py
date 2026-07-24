from __future__ import annotations

import re
from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from minince.shared.exceptions import ValidationError


class TemplateRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            autoescape=False,
        )

    def render(
        self,
        template_content: str,
        variables: dict[str, Any],
        allowed_variables: list[str] | None = None,
    ) -> str:
        self._validate_variables(variables, allowed_variables)

        try:
            template = self._env.from_string(template_content)
            rendered = template.render(**variables)
            return rendered
        except UndefinedError as e:
            raise ValidationError(f"Undefined variable in template: {e}")
        except TemplateSyntaxError as e:
            raise ValidationError(f"Template syntax error: {e}")
        except Exception as e:
            raise ValidationError(f"Template rendering failed: {e}")

    def get_template_variables(self, template_content: str) -> list[str]:
        pattern = r'\{\{\s*(\w+(?:\.\w+)*)\s*\}\}'
        variables = re.findall(pattern, template_content)
        return sorted(set(variables))

    def validate_template(
        self,
        template_content: str,
        variable_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        found_variables = self.get_template_variables(template_content)

        result = {
            "valid": True,
            "template_variables": found_variables,
            "schema_variables": [],
            "missing_in_schema": [],
            "extra_in_schema": [],
        }

        if variable_schema:
            schema_vars = list(variable_schema.keys())
            result["schema_variables"] = schema_vars

            missing = set(found_variables) - set(schema_vars)
            result["missing_in_schema"] = sorted(missing)

            extra = set(schema_vars) - set(found_variables)
            result["extra_in_schema"] = sorted(extra)

            if missing:
                result["valid"] = False

        try:
            self._env.from_string(template_content)
        except TemplateSyntaxError as e:
            result["valid"] = False
            result["syntax_error"] = str(e)

        return result

    def _validate_variables(
        self,
        variables: dict[str, Any],
        allowed_variables: list[str] | None,
    ) -> None:
        if allowed_variables is not None:
            invalid_vars = set(variables.keys()) - set(allowed_variables)
            if invalid_vars:
                raise ValidationError(
                    f"Invalid variables: {', '.join(sorted(invalid_vars))}. "
                    f"Allowed: {', '.join(sorted(allowed_variables))}"
                )

    def create_safe_template(
        self,
        template_content: str,
        allowed_variables: list[str],
    ) -> SafeTemplate:
        return SafeTemplate(self, template_content, allowed_variables)


class SafeTemplate:
    def __init__(
        self,
        renderer: TemplateRenderer,
        template_content: str,
        allowed_variables: list[str],
    ) -> None:
        self._renderer = renderer
        self._template_content = template_content
        self._allowed_variables = allowed_variables
        self._available_variables = renderer.get_template_variables(template_content)

    @property
    def required_variables(self) -> list[str]:
        return self._available_variables

    @property
    def allowed_variables(self) -> list[str]:
        return self._allowed_variables

    def render(self, **variables: Any) -> str:
        self._check_required_variables(variables)
        return self._renderer.render(
            self._template_content,
            variables,
            self._allowed_variables,
        )

    def _check_required_variables(self, variables: dict[str, Any]) -> None:
        missing = set(self._available_variables) - set(variables.keys())
        if missing:
            raise ValidationError(
                f"Missing required variables: {', '.join(sorted(missing))}"
            )


def create_vlan_template(vlan_id_var: str = "vlan_id", name_var: str = "name") -> str:
    return f"""system-view
vlan {{{{ {vlan_id_var} }}}}
 name {{{{ {name_var} }}}}
quit
"""


def create_interface_template(
    ifname_var: str = "interface_name",
    desc_var: str = "description",
) -> str:
    return f"""system-view
interface {{{{ {ifname_var} }}}}
 description {{{{ {desc_var} }}}}
quit
"""


def create_access_interface_template(
    ifname_var: str = "interface_name",
    vlan_var: str = "access_vlan",
) -> str:
    return f"""system-view
interface {{{{ {ifname_var} }}}}
 port link-type access
 port default vlan {{{{ {vlan_var} }}}}
quit
"""


def create_trunk_interface_template(
    ifname_var: str = "interface_name",
    vlans_var: str = "allowed_vlans",
) -> str:
    return f"""system-view
interface {{{{ {ifname_var} }}}}
 port link-type trunk
 port trunk allow-pass vlan {{{{ {vlans_var} }}}}
quit
"""
