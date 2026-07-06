"""
Tests for the Event Bus.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_reach.core.engine.events import EventBus


async def test_subscribe_and_publish() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        received.append({"type": event_type, "payload": payload})

    bus.subscribe("test.event", handler)
    await bus.publish("test.event", {"message": "hello"})

    assert len(received) == 1
    assert received[0]["type"] == "test.event"
    assert received[0]["payload"]["message"] == "hello"


async def test_multiple_subscribers() -> None:
    bus = EventBus()
    count = 0

    async def handler1(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal count
        count += 1

    async def handler2(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal count
        count += 1

    bus.subscribe("test.event", handler1)
    bus.subscribe("test.event", handler2)
    await bus.publish("test.event", {})

    assert count == 2


async def test_unsubscribe() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("test.event", handler)
    result = bus.unsubscribe("test.event", handler)
    assert result is True

    await bus.publish("test.event", {"message": "hello"})
    assert len(received) == 0


async def test_unsubscribe_not_found() -> None:
    bus = EventBus()

    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        pass

    result = bus.unsubscribe("test.event", handler)
    assert result is False


async def test_publish_no_subscribers() -> None:
    bus = EventBus()
    await bus.publish("test.event", {"message": "hello"})


async def test_handler_exception_does_not_crash_bus() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def bad_handler(event_type: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("handler error")

    async def good_handler(event_type: str, payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("test.event", bad_handler)
    bus.subscribe("test.event", good_handler)
    await bus.publish("test.event", {"message": "hello"})

    assert len(received) == 1


def test_clear() -> None:
    bus = EventBus()

    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        pass

    bus.subscribe("test.event", handler)
    bus.clear()

    assert bus._subscribers == {}
