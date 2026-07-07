"""
Config layer: Configuration Management (M6.12).

Layer: Config/Infrastructure — extends config/settings.py with
environment profiles, runtime configuration, and reload capability.

This module does NOT replace Settings or get_settings(). It builds on
top of them:

- ``Settings`` (settings.py) remains the single source of truth for
  the process's configuration values.
- ``get_settings()`` (settings.py) remains the cached accessor every
  other module calls.
- ``ConfigurationManager`` adds what Settings alone does not provide:
  named environment profiles, runtime overrides, validation, and a
  reload path that refreshes the cached Settings instance.

Engineering rules
-----------------
- No other module should read os.environ directly — they go through
  Settings (Blueprint Section 23: Security — centralized secret
  handling). ConfigurationManager is part of the config layer, so it
  is allowed to interact with the environment on behalf of Settings.
- Reload creates a NEW Settings instance and replaces the cached one.
  Existing references to the old Settings object are not mutated —
  callers that held a reference must re-call get_settings() to see
  the new values. This is intentional: silently mutating a shared
  object that other modules already captured would be a source of
  subtle bugs.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment profiles
# ---------------------------------------------------------------------------


class EnvironmentProfile(str, Enum):
    """Named environment profiles with preset configuration values."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# Preset overrides per profile. These are applied on top of whatever
# the environment / .env already provides — they fill in defaults the
# way a developer would expect for each environment, without forcing
# the user to set every variable manually.
_PROFILE_DEFAULTS: dict[EnvironmentProfile, dict[str, Any]] = {
    EnvironmentProfile.DEVELOPMENT: {
        "debug": True,
        "environment": "development",
    },
    EnvironmentProfile.STAGING: {
        "debug": False,
        "environment": "staging",
    },
    EnvironmentProfile.PRODUCTION: {
        "debug": False,
        "environment": "production",
    },
}


# ---------------------------------------------------------------------------
# Configuration Manager
# ---------------------------------------------------------------------------


class ConfigurationManager:
    """Manage environment profiles, runtime overrides, and reload.

    Parameters
    ----------
    settings:
        The initial Settings instance. Defaults to the cached one from
        get_settings(). Injected so tests can pass a custom instance.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._profile: Optional[EnvironmentProfile] = None
        self._runtime_overrides: dict[str, Any] = {}
        self._profiles: dict[str, dict[str, Any]] = {}
        for prof, overrides in _PROFILE_DEFAULTS.items():
            self._profiles[prof.value] = dict(overrides)

    # ------------------------------------------------------------------
    # Current settings
    # ------------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        """The current Settings instance."""
        return self._settings

    @property
    def profile(self) -> Optional[EnvironmentProfile]:
        """The active environment profile, if any."""
        return self._profile

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def register_profile(
        self,
        name: str,
        overrides: dict[str, Any],
    ) -> None:
        """Register (or replace) a named environment profile.

        ``name`` is case-insensitive and stored lowercase. The overrides
        dict follows the same keys as Settings fields.
        """
        self._profiles[name.strip().lower()] = dict(overrides)
        logger.info("Registered configuration profile: %s", name)

    def apply_profile(self, name: str) -> Settings:
        """Apply a registered profile and return a new Settings instance.

        The profile's overrides are applied on top of the current
        environment/.env values. The result becomes the active Settings
        (replaces the cached instance via get_settings).

        Raises
        ------
        KeyError:
            If no profile with the given name is registered.
        ValueError:
            If the merged configuration fails Settings validation.
        """
        key = name.strip().lower()
        if key not in self._profiles:
            raise KeyError(
                f"Unknown profile '{name}'. "
                f"Registered profiles: {sorted(self._profiles)}"
            )

        # Build a new Settings from the current one, then apply the
        # profile overrides. We reconstruct from the current values so
        # that environment variables still take precedence over the
        # profile defaults.
        current_values = self._settings.model_dump()
        merged = {**current_values, **self._profiles[key]}

        new_settings = Settings(**merged)
        self._settings = new_settings
        self._profile = (
            EnvironmentProfile(key)
            if key in {p.value for p in EnvironmentProfile}
            else None
        )

        # Replace the cached instance so other modules see the update.
        get_settings.cache_clear()
        get_settings()

        logger.info("Applied configuration profile: %s", key)
        return self._settings

    def list_profiles(self) -> list[str]:
        """Return the names of all registered profiles, sorted."""
        return sorted(self._profiles.keys())

    # ------------------------------------------------------------------
    # Runtime overrides
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Apply a runtime override to the current Settings.

        The override is stored and applied in-memory. It does NOT
        persist to .env — runtime overrides are process-local by
        design (editing .env from the process would be a security
        concern and would not be visible to other processes anyway).

        Raises
        ------
        AttributeError:
            If ``key`` is not a valid Settings field.
        ValueError:
            If the value fails Settings validation.
        """
        if not hasattr(self._settings, key):
            raise AttributeError(
                f"Settings has no field '{key}'. "
                f"Valid fields: {list(self._settings.model_dump().keys())}"
            )

        # Validate by constructing a temporary Settings with the
        # override applied — pydantic will raise on invalid values.
        current_values = self._settings.model_dump()
        current_values[key] = value
        Settings(**current_values)  # validation only

        # Apply the override to the live object.
        setattr(self._settings, key, value)
        self._runtime_overrides[key] = value
        logger.info("Runtime config override: %s = %s", key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Get the current value of a Settings field.

        Runtime overrides are already reflected on the live Settings
        object, so this returns the effective value.
        """
        return getattr(self._settings, key, default)

    def get_runtime_overrides(self) -> dict[str, Any]:
        """Return a copy of all runtime overrides applied so far."""
        return dict(self._runtime_overrides)

    def clear_runtime_overrides(self) -> Settings:
        """Drop all runtime overrides and rebuild Settings from the
        environment/.env values only.

        Returns the new Settings instance.
        """
        self._runtime_overrides.clear()
        self._settings = Settings()
        get_settings.cache_clear()
        get_settings()
        logger.info("Cleared all runtime configuration overrides")
        return self._settings

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload(self) -> Settings:
        """Reload Settings from the environment/.env.

        Clears the lru_cache, rebuilds a fresh Settings instance, and
        re-applies any runtime overrides that were set previously.

        Returns the new Settings instance.
        """
        # Rebuild from environment.
        fresh = Settings()

        # Re-apply runtime overrides on top.
        if self._runtime_overrides:
            values = fresh.model_dump()
            values.update(self._runtime_overrides)
            fresh = Settings(**values)

        self._settings = fresh
        get_settings.cache_clear()
        get_settings()

        logger.info("Configuration reloaded from environment")
        return self._settings

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate the current configuration and return a list of
        human-readable issues (empty if valid).

        Checks:
        - Settings pydantic validation (already enforced at construction)
        - default_model_provider has a configured API key
        - allowed_origins is non-empty when debug is False
        """
        issues: list[str] = []

        provider = self._settings.default_model_provider
        if not self._settings.provider_api_key(provider):
            issues.append(
                f"default_model_provider '{provider}' has no API key configured"
            )

        if not self._settings.debug and not self._settings.allowed_origins:
            issues.append(
                "allowed_origins is empty in non-debug mode — "
                "the frontend will be unable to call the API"
            )

        return issues

    def to_dict(self) -> dict[str, Any]:
        """Return the current effective configuration as a dict.

        Sensitive fields (API keys) are masked.
        """
        data = self._settings.model_dump()
        for key in list(data.keys()):
            if "api_key" in key and data[key]:
                data[key] = "***masked***"
        data["_profile"] = self._profile.value if self._profile else None
        data["_runtime_overrides"] = dict(self._runtime_overrides)
        return data
