"""Unit tests for ConfigurationManager (M6.12)."""

from __future__ import annotations

import pytest

from config.configuration import ConfigurationManager, EnvironmentProfile
from config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Ensure each test starts with a fresh cached Settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key")


@pytest.fixture
def manager(settings: Settings) -> ConfigurationManager:
    return ConfigurationManager(settings=settings)


# ---------------------------------------------------------------------------
# EnvironmentProfile
# ---------------------------------------------------------------------------


class TestEnvironmentProfile:
    def test_profile_values(self) -> None:
        assert EnvironmentProfile.DEVELOPMENT.value == "development"
        assert EnvironmentProfile.STAGING.value == "staging"
        assert EnvironmentProfile.PRODUCTION.value == "production"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfiles:
    def test_default_profiles_registered(self, manager: ConfigurationManager) -> None:
        profiles = manager.list_profiles()
        assert "development" in profiles
        assert "staging" in profiles
        assert "production" in profiles

    def test_register_custom_profile(self, manager: ConfigurationManager) -> None:
        manager.register_profile("custom", {"debug": False, "app_name": "Custom"})
        assert "custom" in manager.list_profiles()

    def test_register_profile_case_insensitive(self, manager: ConfigurationManager) -> None:
        manager.register_profile("MyProfile", {"debug": True})
        assert "myprofile" in manager.list_profiles()

    def test_apply_development_profile(self, manager: ConfigurationManager) -> None:
        manager.apply_profile("development")
        assert manager.settings.debug is True
        assert manager.settings.environment == "development"
        assert manager.profile is EnvironmentProfile.DEVELOPMENT

    def test_apply_production_profile(self, manager: ConfigurationManager) -> None:
        manager.apply_profile("production")
        assert manager.settings.debug is False
        assert manager.settings.environment == "production"
        assert manager.profile is EnvironmentProfile.PRODUCTION

    def test_apply_profile_preserves_env_values(
        self, settings: Settings, manager: ConfigurationManager
    ) -> None:
        # The settings fixture has an explicit app_name default; applying
        # a profile should not wipe it.
        original_name = settings.app_name
        manager.apply_profile("staging")
        assert manager.settings.app_name == original_name

    def test_apply_unknown_profile_raises(self, manager: ConfigurationManager) -> None:
        with pytest.raises(KeyError, match="Unknown profile"):
            manager.apply_profile("nonexistent")

    def test_apply_profile_validation(
        self, settings: Settings
    ) -> None:
        # Register a profile with an invalid value (max_subtask_retries < 1).
        mgr = ConfigurationManager(settings=settings)
        mgr.register_profile("bad", {"max_subtask_retries": 0})
        with pytest.raises(ValueError):
            mgr.apply_profile("bad")


# ---------------------------------------------------------------------------
# Runtime overrides
# ---------------------------------------------------------------------------


class TestRuntimeOverrides:
    def test_set_valid_override(self, manager: ConfigurationManager) -> None:
        manager.set("debug", False)
        assert manager.settings.debug is False
        assert manager.get("debug") is False

    def test_set_invalid_field_raises(self, manager: ConfigurationManager) -> None:
        with pytest.raises(AttributeError, match="Settings has no field"):
            manager.set("nonexistent_field", 123)

    def test_set_invalid_value_raises(self, manager: ConfigurationManager) -> None:
        with pytest.raises(ValueError):
            manager.set("max_subtask_retries", -1)

    def test_get_with_default(self, manager: ConfigurationManager) -> None:
        assert manager.get("debug") is True  # default from Settings
        assert manager.get("nonexistent", "fallback") == "fallback"

    def test_get_runtime_overrides(self, manager: ConfigurationManager) -> None:
        manager.set("debug", False)
        manager.set("app_name", "TestApp")
        overrides = manager.get_runtime_overrides()
        assert overrides == {"debug": False, "app_name": "TestApp"}

    def test_clear_runtime_overrides(
        self, manager: ConfigurationManager
    ) -> None:
        manager.set("debug", False)
        assert manager.settings.debug is False
        manager.clear_runtime_overrides()
        # After clearing, Settings is rebuilt from environment — debug
        # reverts to its default (True).
        assert manager.settings.debug is True
        assert manager.get_runtime_overrides() == {}


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_rebuilds_settings(
        self, manager: ConfigurationManager
    ) -> None:
        manager.set("debug", False)
        assert manager.settings.debug is False
        manager.reload()
        # After reload, runtime overrides are re-applied.
        assert manager.settings.debug is False

    def test_reload_without_overrides(
        self, manager: ConfigurationManager
    ) -> None:
        manager.reload()
        # Should succeed and produce a valid Settings instance.
        assert manager.settings is not None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_valid_config(self, manager: ConfigurationManager) -> None:
        # The fixture has an anthropic_api_key set, so validation passes.
        issues = manager.validate()
        assert issues == []

    def test_validate_missing_provider_key(self) -> None:
        settings = Settings(anthropic_api_key=None, default_model_provider="anthropic")
        mgr = ConfigurationManager(settings=settings)
        issues = mgr.validate()
        assert any("no API key" in issue for issue in issues)

    def test_validate_empty_origins_in_production(self) -> None:
        settings = Settings(
            anthropic_api_key="k",
            debug=False,
            allowed_origins=[],
        )
        mgr = ConfigurationManager(settings=settings)
        issues = mgr.validate()
        assert any("allowed_origins" in issue for issue in issues)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_masks_api_keys(
        self, manager: ConfigurationManager
    ) -> None:
        data = manager.to_dict()
        assert data["anthropic_api_key"] == "***masked***"

    def test_to_dict_includes_profile(
        self, manager: ConfigurationManager
    ) -> None:
        manager.apply_profile("production")
        data = manager.to_dict()
        assert data["_profile"] == "production"

    def test_to_dict_includes_overrides(
        self, manager: ConfigurationManager
    ) -> None:
        manager.set("debug", False)
        data = manager.to_dict()
        assert data["_runtime_overrides"] == {"debug": False}
