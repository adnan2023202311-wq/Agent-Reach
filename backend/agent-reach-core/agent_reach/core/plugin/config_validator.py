"""
Plugin configuration validator.

Validates plugin configuration data against the config_schema
defined in a plugin manifest.
"""

from __future__ import annotations

from typing import Any

from ..schemas.resolver import SchemaResolver
from .manifest import PluginManifest


class ConfigValidator:
    """Validates plugin configuration against manifest schemas."""

    def __init__(self, schema_resolver: SchemaResolver | None = None) -> None:
        self._schema_resolver = schema_resolver

    def validate(
        self,
        manifest: PluginManifest,
        config: dict[str, Any],
    ) -> list[str]:
        """Validate configuration against a plugin's config_schema."""
        errors: list[str] = []

        if manifest.config_schema is None:
            return errors

        schema = manifest.config_schema

        required = schema.get("required", [])
        for field in required:
            if field not in config:
                errors.append(f"Required config field '{field}' is missing")

        properties = schema.get("properties", {})
        for field_name, field_value in config.items():
            if field_name in properties:
                expected_type = properties[field_name].get("type")
                if expected_type and not self._check_type(field_value, expected_type):
                    errors.append(
                        f"Config field '{field_name}' has wrong type. "
                        f"Expected {expected_type}"
                    )

        if self._schema_resolver is not None:
            schema_id = schema.get("$id") or schema.get("id")
            if schema_id:
                valid, schema_errors = self._schema_resolver.validate_against_schema(
                    config, schema_id
                )
                if not valid:
                    errors.extend(schema_errors)

        return errors

    def _check_type(self, value: Any, expected_type: str) -> bool:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        python_type = type_map.get(expected_type)
        if python_type:
            return isinstance(value, python_type)

        return True
