"""
Infrastructure layer: ToolManager.

Layer: Adapters.

Central, permissioned, audited access point for external tools (Git,
Docker, Playwright, filesystem, terminal, ...) per Blueprint Section
18. Zero tools are registered yet — this milestone only builds the
mechanism (registration, permission check, audit log) every future
tool will plug into identically.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol


class ToolFunc(Protocol):
    async def __call__(self, **kwargs: Any) -> Any: ...


logger = logging.getLogger(__name__)


class ToolManager:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFunc] = {}
        self._permissions: dict[str, frozenset[str]] = {}

    def register(
        self,
        name: str,
        func: ToolFunc,
        allowed_agents: Optional[frozenset[str]] = None,
    ) -> None:
        self._tools[name] = func
        self._permissions[name] = allowed_agents or frozenset()
        logger.info("registered tool: %s", name)

    async def call(self, name: str, agent_type: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")

        allowed = self._permissions[name]
        if allowed and agent_type not in allowed:
            raise PermissionError(
                f"Agent '{agent_type}' is not permitted to use tool '{name}'"
            )

        logger.info("audit: agent=%s tool=%s kwargs=%s", agent_type, name, kwargs)
        # TODO(next milestone): route through a sandbox when
        # config.settings.enable_sandboxed_execution is True
        # (Blueprint Section 23: Security).
        return await self._tools[name](**kwargs)


# TODO(next milestone): populate with real tools, e.g.
#   tool_manager.register("git_clone", git_clone_fn, allowed_agents=frozenset({"coding"}))
