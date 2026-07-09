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

    def provider_api_key(self, provider: str) -> Optional[str]:
        """Look up an API key by provider name (Blueprint Section 19)."""
        return getattr(self, f"{provider}_api_key", None)

    def is_provider_ready(self, provider: str) -> bool:
        """Whether `provider` both has a key configured AND has a working
        ModelClient implementation. Only "anthropic" satisfies the second
        condition today (infrastructure/model_client.py) — see
        domain/interfaces.py's ModelClient docstring for why a real
        multi-provider router doesn't exist yet. A provider with a key
        but no client implementation is still reported as not ready:
        the key alone can't do anything yet.
        """
        return provider == self.default_model_provider and bool(self.provider_api_key(provider))

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
