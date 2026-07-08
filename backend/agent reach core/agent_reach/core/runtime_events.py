"""
Event-Driven Runtime (M9.24).

Layer: Application/Core.

Reuses the EXISTING EventBus from the plugin core (agent-reach-core's
agent_reach.core.engine.events) — the M2 pub/sub mechanism — rather
than introducing a second bus. This module adds what M9.24 needs on
top of it:

- Canonical runtime event names (RuntimeEvent) so publishers and
  subscribers agree on the vocabulary from the spec's chain:
      ConversationCreated → MemoryUpdated → KnowledgeUpdated →
      LearningTriggered → ReflectionTriggered → AnalyticsUpdated
- RuntimeEventHub: wraps the bus with a bounded, timestamped event
  log so the event stream is observable through the API (every event
  that flowed is a real, inspectable record).

The hub is composed around the bus (not a subclass): subscribers can
still be registered directly on the underlying bus by plugins, and
everything published through the hub reaches them.
"""

from __future__ import annotations

import sys
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Same path bridge the plugin agent uses to reach agent-reach-core.
_ARK_CORE = Path(__file__).resolve().parent.parent.parent.parent / "agent-reach-core"
if str(_ARK_CORE) not in sys.path:
    sys.path.insert(0, str(_ARK_CORE))

from agent_reach.core.engine.events import EventBus  # noqa: E402


class RuntimeEvent:
    """Canonical event names for the M9.24 event chain."""

    CONVERSATION_CREATED = "conversation.created"
    PIPELINE_STARTED = "pipeline.started"
    ROUTER_DECIDED = "router.decided"
    MEMORY_UPDATED = "memory.updated"
    CONTEXT_BUILT = "context.built"
    KNOWLEDGE_UPDATED = "knowledge.updated"
    REFLECTION_TRIGGERED = "reflection.triggered"
    LEARNING_TRIGGERED = "learning.triggered"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    ANALYTICS_UPDATED = "analytics.updated"
    TOOL_EXECUTED = "tool.executed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_FINISHED = "workflow.finished"

    @classmethod
    def all(cls) -> list[str]:
        return [
            value
            for name, value in vars(cls).items()
            if isinstance(value, str) and not name.startswith("_")
        ]


@dataclass
class RecordedEvent:
    """One event that flowed through the hub."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }


class RuntimeEventHub:
    """The existing EventBus + a bounded observable event log.

    Parameters
    ----------
    bus:
        An existing EventBus to publish through. A fresh one is
        created when omitted (each hub then owns its bus — the
        composition root decides which instance is shared).
    max_log:
        Bound on the recorded event log.
    """

    def __init__(self, bus: Optional[EventBus] = None, max_log: int = 2000) -> None:
        if max_log < 1:
            raise ValueError("max_log must be >= 1")
        self._bus = bus or EventBus()
        self._log: deque[RecordedEvent] = deque(maxlen=max_log)

    @property
    def bus(self) -> EventBus:
        """The underlying EventBus (for direct subscriber registration)."""
        return self._bus

    # ── Publish / subscribe ─────────────────────────────────────

    async def publish(self, event_type: str, payload: dict[str, Any]) -> RecordedEvent:
        """Record the event, then fan out through the existing bus."""
        record = RecordedEvent(event_type=event_type, payload=dict(payload))
        self._log.append(record)
        await self._bus.publish(event_type, payload)
        return record

    def subscribe(self, event_type: str, handler: Any) -> None:
        self._bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: str, handler: Any) -> bool:
        return self._bus.unsubscribe(event_type, handler)

    # ── Observability ───────────────────────────────────────────

    def get_events(
        self,
        event_type: str = "",
        limit: int = 100,
        since: float = 0.0,
    ) -> list[RecordedEvent]:
        """Recent events, newest first, optionally filtered."""
        events = list(self._log)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if since > 0:
            events = [e for e in events if e.timestamp > since]
        return list(reversed(events))[: max(0, limit)]

    def get_stats(self) -> dict[str, Any]:
        """Counts per event type plus totals — all from real traffic."""
        counts = Counter(e.event_type for e in self._log)
        return {
            "total_events": len(self._log),
            "by_type": dict(counts),
            "known_types": RuntimeEvent.all(),
        }

    def clear(self) -> None:
        """Drop the log (subscribers are untouched). For testing."""
        self._log.clear()
