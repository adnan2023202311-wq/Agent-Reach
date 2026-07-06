"""
Event bus for inter-plugin communication.

Provides a lightweight in-memory publish/subscribe mechanism
for plugins to emit and listen to events without direct coupling.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine


EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """In-memory event bus for plugin communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Unsubscribe from an event type."""
        if event_type not in self._subscribers:
            return False
        try:
            self._subscribers[event_type].remove(handler)
            return True
        except ValueError:
            return False

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_type, payload)
            except Exception:
                continue

    def clear(self) -> None:
        """Remove all subscribers. Useful for testing."""
        self._subscribers.clear()
