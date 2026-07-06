"""
Tests for the Plugin Configuration Validator.
"""

from __future__ import annotations

import pytest

from agent_reach.core.plugin.config_validator import ConfigValidator
from agent_reach.core.plugin.manifest import PluginManifest


def test_validate_no_schema() -> None:
    validator = ConfigValidator()
    manifest = PluginManifest(
        id="test.plugin",
        name="Test Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
    )

    errors = validator.validate(manifest, {"anything": "goes"})
    assert errors == []


def test_validate_required_fields() -> None:
    validator = ConfigValidator()
    manifest = PluginManifest(
        id="test.plugin",
        name="Test Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        config_schema={
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string"},
            },
        },
    )

    errors = validator.validate(manifest, {})
    assert len(errors) == 1
    assert "Required config field 'api_key' is missing" in errors[0]


def test_validate_valid_config() -> None:
    validator = ConfigValidator()
    manifest = PluginManifest(
        id="test.plugin",
        name="Test Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        config_schema={
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string"},
                "timeout": {"type": "integer"},
            },
        },
    )

    errors = validator.validate(manifest, {"api_key": "secret", "timeout": 30})
    assert errors == []


def test_validate_wrong_type() -> None:
    validator = ConfigValidator()
    manifest = PluginManifest(
        id="test.plugin",
        name="Test Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        config_schema={
            "type": "object",
            "properties": {
                "timeout": {"type": "integer"},
            },
        },
    )

    errors = validator.validate(manifest, {"timeout": "not an integer"})
    assert len(errors) == 1
    assert "timeout" in errors[0]
    assert "wrong type" in errors[0]


def test_validate_multiple_errors() -> None:
    validator = ConfigValidator()
    manifest = PluginManifest(
        id="test.plugin",
        name="Test Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        config_schema={
            "type": "object",
            "required": ["api_key", "endpoint"],
            "properties": {
                "api_key": {"type": "string"},
                "timeout": {"type": "integer"},
            },
        },
    )

    errors = validator.validate(manifest, {"timeout": "bad"})
    assert len(errors) == 3
