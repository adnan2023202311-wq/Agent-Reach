"""
Infrastructure layer: Provider Config Store (M9 fix).

Persists provider credentials (API keys, base URLs, default models)
configured via the Settings → Providers UI to a JSON file on disk.

Before this store existed, the backend could only read provider keys
from environment variables (config/settings.py). The Settings UI had
a "Save" button that updated only frontend React state — nothing
reached the backend, so GET /api/v1/providers always returned
"unconfigured" and chat execution always failed with "X provider
requires an API key".

The store is intentionally simple: a single JSON file at
``data/provider_config.json`` (path configurable via the
``PROVIDER_CONFIG_PATH`` env var). It's read on every access so
changes take effect immediately without a restart. Writes are
atomic (write to temp file, then rename).

Security note: the file contains API keys in plaintext. This is
acceptable for a single-user dev/workstation deployment (the same
trust model as a .env file). For multi-user production, wrap this
store with encryption at rest — but don't change the interface.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default location for the persisted provider config.
#
# M9 fix (v2.7): previously this used ``Path.cwd()`` which made the
# path depend on WHERE the process was launched from. The backend
# server (uvicorn) typically runs from the ``agent_reach/`` directory,
# so the file landed at ``agent_reach/data/provider_config.json``. But
# when the user runs a one-liner like ``python -c "from config.settings
# import get_settings; ..."`` from the project root or a different
# directory, ``Path.cwd()`` pointed elsewhere, the store found no file,
# and ``Settings.provider_api_key()`` returned None — making it look
# like the fix didn't work.
#
# The fix anchors the path to THIS MODULE's location (the
# ``infrastructure/`` package dir inside ``agent_reach/``), then goes
# up one level and into ``data/``. That makes the path stable
# regardless of the process's working directory. The env var
# ``PROVIDER_CONFIG_PATH`` still wins for tests / custom deployments.
_MODULE_DIR = Path(__file__).resolve().parent  # .../agent_reach/infrastructure/
_BACKEND_ROOT = _MODULE_DIR.parent             # .../agent_reach/
_DEFAULT_CONFIG_PATH = os.environ.get(
    "PROVIDER_CONFIG_PATH",
    str(_BACKEND_ROOT / "data" / "provider_config.json"),
)


class ProviderConfigStore:
    """File-backed store for provider credentials configured via the UI.

    Each provider's record is a dict with optional keys:
        api_key: str        — the provider's API key
        base_url: str       — custom base URL (overrides the provider default)
        default_model: str  — preferred model for this provider
        enabled: bool       — whether the user enabled this provider

    The store merges with environment variables: env vars take
    precedence (so ops can override UI-configured keys), but the store
    is the fallback when an env var isn't set.
    """

    def __init__(self, path: str = _DEFAULT_CONFIG_PATH) -> None:
        self._path = Path(path)
        self._lock = Lock()
        self._cache: Optional[dict[str, dict[str, Any]]] = None
        # Ensure the parent directory exists so the first save doesn't
        # fail with FileNotFoundError.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        """Return one provider's stored config (empty dict if none)."""
        data = self._load()
        return dict(data.get(provider_id, {}))

    def get_api_key(self, provider_id: str) -> Optional[str]:
        """Convenience: just the API key for a provider."""
        return self.get_provider(provider_id).get("api_key") or None

    def get_base_url(self, provider_id: str) -> Optional[str]:
        return self.get_provider(provider_id).get("base_url") or None

    def get_default_model(self, provider_id: str) -> Optional[str]:
        return self.get_provider(provider_id).get("default_model") or None

    def is_enabled(self, provider_id: str) -> bool:
        return bool(self.get_provider(provider_id).get("enabled", False))

    def list_configured(self) -> list[str]:
        """Provider IDs that have a non-empty api_key in the store."""
        data = self._load()
        return [
            pid for pid, cfg in data.items()
            if cfg.get("api_key")
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_provider(self, provider_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge ``patch`` into a provider's stored config and persist.

        Returns the updated provider config dict. Only the keys present
        in ``patch`` are overwritten; other keys are preserved. To
        clear a key, set it to ``None`` or ``""`` in the patch.
        """
        with self._lock:
            data = self._load_raw()
            current = dict(data.get(provider_id, {}))
            for k, v in patch.items():
                if v is None or v == "":
                    current.pop(k, None)
                else:
                    current[k] = v
            # If we have an api_key, mark enabled=True automatically
            # (the user just configured it — that means they want it on).
            if current.get("api_key"):
                current["enabled"] = True
            data[provider_id] = current
            self._save_raw(data)
            logger.info(
                "ProviderConfigStore: updated %s (keys: %s)",
                provider_id,
                ", ".join(current.keys()),
            )
            return dict(current)

    def delete_provider(self, provider_id: str) -> bool:
        """Remove a provider's stored config. Returns True if it existed."""
        with self._lock:
            data = self._load_raw()
            if provider_id not in data:
                return False
            del data[provider_id]
            self._save_raw(data)
            logger.info("ProviderConfigStore: deleted %s", provider_id)
            return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load and cache the config. Re-reads on every call so
        external changes (e.g. another process writing the file) are
        picked up. The cache is only to avoid re-reading within the
        same call.
        """
        return self._load_raw()

    def _load_raw(self) -> dict[str, dict[str, Any]]:
        try:
            if not self._path.exists():
                return {}
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(
                    "ProviderConfigStore: %s is not a JSON object — ignoring",
                    self._path,
                )
                return {}
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ProviderConfigStore: could not read %s: %s", self._path, exc)
            return {}

    def _save_raw(self, data: dict[str, dict[str, Any]]) -> None:
        """Atomic write: write to temp file in the same dir, then rename."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # NamedTemporaryFile + os.replace for atomicity on POSIX.
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=".provider_config_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_path, self._path)
        except Exception:
            # Clean up the temp file if the write failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ── Module-level singleton ──────────────────────────────────────────────
# Lazily instantiated so the env var is read at first use, not at import
# time (tests can set PROVIDER_CONFIG_PATH before importing).
_store: Optional[ProviderConfigStore] = None


def get_provider_config_store() -> ProviderConfigStore:
    """Return the process-wide ProviderConfigStore singleton."""
    global _store
    if _store is None:
        _store = ProviderConfigStore()
    return _store
