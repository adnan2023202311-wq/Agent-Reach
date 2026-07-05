"""
Infrastructure layer: in-memory session store.

Layer: Adapters.

A plain concrete class, not an implementation of an interface — there
is only one implementation and nothing calls it yet (MainController
doesn't use memory this milestone; see docs/ARCHITECTURE.md,
"Remaining weaknesses"). If a second implementation (e.g. SQLite-backed,
for persistence across restarts) is added later and needs to be
swappable with this one, extract a MemoryStore interface in
domain/interfaces.py at that point — not before.
"""

from __future__ import annotations

from typing import Any, Optional


class InMemoryStore:
    """Session-scoped key/value store. Not persistent across restarts."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def save(self, session_id: str, key: str, value: Any) -> None:
        self._data.setdefault(session_id, {})[key] = value

    async def load(self, session_id: str, key: str) -> Optional[Any]:
        return self._data.get(session_id, {}).get(key)

    async def history(self, session_id: str) -> list[dict[str, Any]]:
        return [self._data.get(session_id, {})]
