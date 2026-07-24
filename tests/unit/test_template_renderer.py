from __future__ import annotations

import pytest

from minince.application.services.template_renderer import (
    SafeTemplate,
    TemplateRenderer,
    create_access_interface_template,
    create_interface_template,
    create_trunk_interface_template,
    create_vlan_template,
)
from minince.shared.exceptions import ValidationError


class TestTemplateRenderer:
    def setup_method(self) -> None:
        self.renderer = TemplateRenderer()

    def test_simple_render(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        result = self.renderer.render(template, {"vlan_id": 100, "name": "TEST"})
        assert "vlan 100" in result
        assert "name TEST" in result

    def test_get_template_variables(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}\n description {{ desc }}"
        variables = self.renderer.get_template_variables(template)
        assert "vlan_id" in variables
        assert "name" in variables
        assert "desc" in variables
        assert len(variables) == 3

    def test_validate_template_valid(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        schema = {"vlan_id": "int", "name": "str"}
        result = self.renderer.validate_template(template, schema)
        assert result["valid"] is True
        assert len(result["missing_in_schema"]) == 0

    def test_validate_template_missing_in_schema(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ unknown_var }}"
        schema = {"vlan_id": "int"}
        result = self.renderer.validate_template(template, schema)
        assert result["valid"] is False
        assert "unknown_var" in result["missing_in_schema"]

    def test_validate_template_extra_in_schema(self) -> None:
        template = "vlan {{ vlan_id }}"
        schema = {"vlan_id": "int", "unused_var": "str"}
        result = self.renderer.validate_template(template, schema)
        assert "unused_var" in result["extra_in_schema"]

    def test_validate_template_syntax_error(self) -> None:
        template = "vlan {{ vlan_id }}\n {% invalid %}"
        result = self.renderer.validate_template(template)
        assert result["valid"] is False
        assert "syntax_error" in result

    def test_render_with_whitelist_valid(self) -> None:
        template = "vlan {{ vlan_id }}"
        result = self.renderer.render(
            template,
            {"vlan_id": 100},
            allowed_variables=["vlan_id"],
        )
        assert "100" in result

    def test_render_with_whitelist_invalid(self) -> None:
        template = "vlan {{ vlan_id }}"
        with pytest.raises(ValidationError, match="Invalid variables"):
            self.renderer.render(
                template,
                {"vlan_id": 100, "bad_var": "test"},
                allowed_variables=["vlan_id"],
            )

    def test_render_missing_variable(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        with pytest.raises(ValidationError, match="Undefined variable"):
            self.renderer.render(template, {"vlan_id": 100})


class TestSafeTemplate:
    def setup_method(self) -> None:
        self.renderer = TemplateRenderer()

    def test_create_safe_template(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        safe = self.renderer.create_safe_template(template, ["vlan_id", "name"])
        assert "vlan_id" in safe.required_variables
        assert "name" in safe.required_variables

    def test_safe_template_render(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        safe = self.renderer.create_safe_template(template, ["vlan_id", "name"])
        result = safe.render(vlan_id=100, name="TEST")
        assert "vlan 100" in result
        assert "name TEST" in result

    def test_safe_template_missing_required(self) -> None:
        template = "vlan {{ vlan_id }}\n name {{ name }}"
        safe = self.renderer.create_safe_template(template, ["vlan_id", "name"])
        with pytest.raises(ValidationError, match="Missing required variables"):
            safe.render(vlan_id=100)

    def test_safe_template_invalid_variable(self) -> None:
        template = "vlan {{ vlan_id }}"
        safe = self.renderer.create_safe_template(template, ["vlan_id"])
        with pytest.raises(ValidationError, match="Invalid variables"):
            safe.render(vlan_id=100, bad_var="test")


class TestTemplateHelpers:
    def test_create_vlan_template(self) -> None:
        template = create_vlan_template()
        assert "{{ vlan_id }}" in template
        assert "{{ name }}" in template
        assert "system-view" in template

    def test_create_interface_template(self) -> None:
        template = create_interface_template()
        assert "{{ interface_name }}" in template
        assert "{{ description }}" in template

    def test_create_access_interface_template(self) -> None:
        template = create_access_interface_template()
        assert "port link-type access" in template
        assert "{{ access_vlan }}" in template

    def test_create_trunk_interface_template(self) -> None:
        template = create_trunk_interface_template()
        assert "port link-type trunk" in template
        assert "{{ allowed_vlans }}" in template

    def test_custom_variable_names(self) -> None:
        template = create_vlan_template(vlan_id_var="vid", name_var="vname")
        assert "{{ vid }}" in template
        assert "{{ vname }}" in template
