"""
SDK layer: Official Python SDK for Agent-Reach (M6.14).

Layer: Interface/Presentation (outermost).

Provides a simple, high-level Python API for interacting with the
Agent-Reach platform. The SDK wraps the ConversationEngine and
SessionManager to give users a clean interface:

    from agent_reach import AgentReach

    app = AgentReach()
    result = app.run("Research the best OCR libraries in Python.")
    print(result.answer)

The SDK can work in two modes:
1. **In-process mode** (default): builds the controller, conversation
   engine, and session manager in-process. No server required.
2. **Remote mode**: connects to a running Agent-Reach server via HTTP.
   The ``base_url`` parameter specifies the server URL.

Design notes
------------
- The SDK is a thin wrapper around the existing components. It does
  not add new functionality — it provides a simpler API.
- In-process mode is the default because it has zero external
  dependencies (no server to start).
- Remote mode uses httpx for HTTP communication.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentReachResult:
    """Result of running a request through the SDK.

    Attributes:
        answer: the final answer text.
        session_id: the session ID (if sessions are used).
        plan_id: the plan ID from the controller.
        status: the task status ("succeeded" or "failed").
        results: list of individual agent results.
    """

    def __init__(
        self,
        answer: str = "",
        session_id: str = "",
        plan_id: str = "",
        status: str = "",
        results: Optional[list[Any]] = None,
    ) -> None:
        self.answer = answer
        self.session_id = session_id
        self.plan_id = plan_id
        self.status = status
        self.results = results or []

    def __repr__(self) -> str:
        return (
            f"AgentReachResult(status={self.status!r}, "
            f"answer={self.answer[:50]!r}...)"
        )


class AgentReach:
    """Official Python SDK for Agent-Reach.

    Parameters
    ---
    api_key:
        Optional API key for authentication (remote mode).
    base_url:
        Base URL for a running Agent-Reach server. If None, the SDK
        runs in in-process mode.
    provider:
        Default model provider (e.g. "anthropic", "openai").
    model:
        Default model name.
    memory_window:
        Number of recent conversation turns to include as context.
        0 disables memory. Defaults to 10.
    user_id:
        Optional user ID for session tracking.
    config:
        Additional configuration dict (passed to Settings).

    Examples
    --------
    In-process mode::

        from agent_reach import AgentReach

        app = AgentReach()
        result = app.run("What is the capital of France?")
        print(result.answer)

    Remote mode::

        app = AgentReach(base_url="http://localhost:8000")
        result = app.run("What is the capital of France?")
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: Optional[str] = None,
        provider: str = "anthropic",
        model: str = "",
        memory_window: int = 10,
        user_id: str = "",
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._provider = provider
        self._model = model
        self._memory_window = memory_window
        self._user_id = user_id
        self._config = config or {}

        # In-process components (lazy-initialized).
        self._conversation_engine = None
        self._session_manager = None
        self._session_id = ""

        # Remote mode HTTP client (lazy-initialized).
        self._http_client = None

        if base_url:
            self._init_remote_mode()
        else:
            self._init_in_process_mode()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_in_process_mode(self) -> None:
        """Set up in-process mode with local components."""
        from composition import build_conversation_engine
        from config.settings import Settings

        # Build settings with overrides.
        settings_kwargs = dict(self._config)
        if self._provider:
            settings_kwargs["default_model_provider"] = self._provider
        if self._model:
            settings_kwargs["default_model"] = self._model

        settings = Settings(**settings_kwargs)
        self._conversation_engine = build_conversation_engine(settings)
        self._session_manager = self._conversation_engine._session_manager

    def _init_remote_mode(self) -> None:
        """Set up remote mode with an HTTP client."""
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for remote mode. "
                "Install it with: pip install httpx"
            ) from exc

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        self._http_client = httpx.Client(
            base_url=self._base_url or "",
            headers=headers,
            timeout=120.0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        message: str,
        *,
        session_id: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> AgentReachResult:
        """Run a request and return the result.

        If no session_id is provided, a new session is created for
        each call (stateless mode). If you want multi-turn
        conversations, pass the session_id from a previous call.

        Parameters
        ----------
        message:
            The user's request.
        session_id:
            Optional session ID for multi-turn conversations.
        context:
            Optional additional context for this turn.

        Returns
        -------
        AgentReachResult with the answer and metadata.
        """
        if self._http_client is not None:
            return self._run_remote(message, session_id=session_id, context=context)
        return self._run_in_process(message, session_id=session_id, context=context)

    def _run_in_process(
        self,
        message: str,
        *,
        session_id: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> AgentReachResult:
        """Run a request in-process."""
        # Create a new session if none provided.
        if not session_id:
            session = self._session_manager.create_session(user_id=self._user_id)
            session_id = session.session_id
        elif not self._session_manager.get_session(session_id):
            # Session doesn't exist — create it.
            session = self._session_manager.create_session(
                user_id=self._user_id,
            )
            session_id = session.session_id

        import asyncio

        result = asyncio.run(
            self._conversation_engine.send_message(
                session_id,
                message,
                extra_context=context,
            )
        )

        return AgentReachResult(
            answer=result.assistant_message.content,
            session_id=session_id,
            plan_id=result.outcome.plan.id if result.outcome else "",
            status=result.outcome.status.value if result.outcome else "unknown",
            results=result.outcome.results if result.outcome else [],
        )

    def _run_remote(
        self,
        message: str,
        *,
        session_id: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> AgentReachResult:
        """Run a request against a remote server."""
        import httpx

        # Create a session if none provided.
        if not session_id:
            resp = self._http_client.post(
                "/api/v1/conversations/sessions",
                json={"user_id": self._user_id},
            )
            resp.raise_for_status()
            session_id = resp.json()["session_id"]

        # Send the message.
        resp = self._http_client.post(
            f"/api/v1/conversations/sessions/{session_id}/messages",
            json={
                "session_id": session_id,
                "message": message,
                "context": context or {},
            },
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Request failed: {exc.response.status_code} "
                f"{exc.response.text}"
            ) from exc

        data = resp.json()
        return AgentReachResult(
            answer=data.get("content", ""),
            session_id=session_id,
            plan_id=data.get("plan_id", ""),
            status=data.get("status", "unknown"),
        )

    def new_session(self, user_id: str = "") -> str:
        """Create a new conversation session and return its ID.

        Useful for multi-turn conversations where you want to manage
        the session explicitly.
        """
        if self._session_manager is None:
            raise RuntimeError("Sessions are not available in remote mode")
        session = self._session_manager.create_session(
            user_id=user_id or self._user_id,
        )
        return session.session_id

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return the conversation history for a session."""
        if self._conversation_engine is None:
            raise RuntimeError("History is not available in remote mode")
        history = self._conversation_engine.get_history(session_id)
        return [m.to_dict() for m in history]

    def close_session(self, session_id: str) -> bool:
        """Terminate a conversation session."""
        if self._session_manager is None:
            raise RuntimeError("Sessions are not available in remote mode")
        return self._session_manager.terminate_session(session_id)

    def close(self) -> None:
        """Close the SDK and release resources."""
        if self._http_client is not None:
            self._http_client.close()

    def __enter__(self) -> "AgentReach":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
