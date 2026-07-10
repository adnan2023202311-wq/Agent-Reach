"""
Config layer: application configuration management.

Layer: Config/Infrastructure — may depend on domain/ (for RetryPolicy),
but nothing in domain/, core/, or agents/ may import this module
directly. They receive the values they need as constructor arguments
instead (see composition.py) — this is what lets core/dispatcher.py
be unit-tested without an environment or a .env file (see
tests/test_dispatcher.py).

Every value here is read from the environment / .env exactly once and
cached via get_settings(). No other module should read os.environ
directly (Blueprint Section 23: Security — centralized secret handling).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.models import RetryPolicy

# Providers Settings actually has a key field for. Used by
# api/routers/providers.py and api/routers/agents.py so both report
# against the same list instead of each hardcoding their own — this is
# NOT the full Blueprint Section 19 provider list (which also names
# Qwen, Zhipu, local/free providers); it's deliberately just the ones
# this config class can actually answer "is a key configured?" for.
KNOWN_PROVIDERS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "google",
    "deepseek",
    "groq",
    "openrouter",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "Agent Reach"
    environment: str = "development"  # development | staging | production
    debug: bool = True

    # --- Model providers (Blueprint Section 19: Model Router) ---
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    default_model_provider: str = "anthropic"
    default_model: str = "claude-sonnet-5"

    # --- Orchestration / retry policy ---
    max_subtask_retries: int = 3
    retry_backoff_seconds: float = 1.5
    task_timeout_seconds: float = 120.0

    # --- Memory (Blueprint Section 16) ---
    memory_backend: str = "in_memory"  # in_memory | sqlite
    memory_db_path: str = "./data/agent_reach.db"

    # --- Security (Blueprint Section 23) ---
    # The Lovable frontend (frontend/) runs as its own Vite/TanStack Start
    # dev server, a different origin from the FastAPI backend — hence CORS.
    # Confirm the actual port `bun run dev` prints and update .env if it
    # differs from these two common defaults.
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]
    enable_sandboxed_execution: bool = True

    @field_validator("max_subtask_retries")
    @classmethod
    def _at_least_one_attempt(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_subtask_retries must be >= 1")
        return value

    @field_validator("retry_backoff_seconds", "task_timeout_seconds")
    @classmethod
    def _must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be a positive number")
        return value

    # M9 fix: the API/config layer uses "google" (KNOWN_PROVIDERS,
    # google_api_key field, /api/v1/providers?id=google) while the
    # runtime ProviderManager uses "gemini" (SUPPORTED_PROVIDERS). When
    # the runtime asks Settings for "gemini", we must check the "google"
    # env var and store entry. This map bridges the two namespaces in
    # BOTH directions — a lookup for either name finds the key.
    _PROVIDER_ALIASES: dict[str, str] = {
        "google": "gemini",
        "gemini": "google",
    }

    def provider_api_key(self, provider: str) -> Optional[str]:
        """Look up an API key by provider name (Blueprint Section 19).

        M9 fix: returns the env-var key if set, otherwise falls back to
        the persisted ProviderConfigStore (data/provider_config.json).
        This makes keys saved via the Settings → Providers UI visible
        to every caller of Settings — the providers router, the
        ProviderManager, is_provider_ready(), etc. — without each one
        needing its own store-reading logic.

        Env vars take precedence so ops can override UI-configured keys.

        M9 fix (v2.8): also checks the provider alias (google↔gemini)
        so a key saved under "google" is found when the runtime asks
        for "gemini", and vice versa.
        """
        # Try the requested name first, then its alias.
        for name in (provider, self._PROVIDER_ALIASES.get(provider, "")):
            if not name:
                continue
            env_key = getattr(self, f"{name}_api_key", None)
            if env_key:
                return env_key
        # Fall back to the persisted config store — try both names.
        try:
            from infrastructure.provider_config_store import get_provider_config_store
            store = get_provider_config_store()
            for name in (provider, self._PROVIDER_ALIASES.get(provider, "")):
                if not name:
                    continue
                key = store.get_api_key(name)
                if key:
                    return key
        except Exception:  # noqa: BLE001 — never break over config lookup
            pass
        return None

    def is_provider_ready(self, provider: str) -> bool:
        """Whether ``provider`` has an API key configured (from env OR store).

        M9 fix: previously this returned True only for the
        ``default_model_provider`` (anthropic), because the old comment
        claimed only Anthropic had a ModelClient implementation. That's
        no longer true — infrastructure/provider_manager.py now builds
        clients for OpenAI, Gemini, OpenRouter, DeepSeek, and Ollama
        via the OpenAI-compatible endpoint. So any provider with a key
        is "ready".

        The key can come from an environment variable OR from the
        persisted ProviderConfigStore (saved via the Settings UI).
        """
        return bool(self.provider_api_key(provider))

    def to_retry_policy(self) -> RetryPolicy:
        """Project the orchestration fields into a narrow value object.

        AgentDispatcher depends on RetryPolicy (3 fields), not on the
        entire Settings object (Interface Segregation Principle) — it
        has no reason to know about API keys or CORS origins.
        """
        return RetryPolicy(
            max_attempts=self.max_subtask_retries,
            backoff_seconds=self.retry_backoff_seconds,
            timeout_seconds=self.task_timeout_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    """Settings are parsed from the environment once per process and cached."""
    return Settings()
