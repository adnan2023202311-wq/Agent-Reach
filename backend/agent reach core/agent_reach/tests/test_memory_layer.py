"""Tests for Memory Layer (M4.7)."""

from __future__ import annotations

import time

import pytest

from memory.layer import MemoryItem, MemoryLayer, MemoryType


class TestMemoryLayer:
    def test_store_and_get(self) -> None:
        layer = MemoryLayer()
        mid = layer.store("hello", importance=0.8)
        item = layer.get(mid)
        assert item is not None
        assert item.content == "hello"
        assert item.importance == 0.8
        assert item.memory_type == MemoryType.SHORT_TERM
        assert item.access_count == 1

    def test_retrieve_relevant(self) -> None:
        layer = MemoryLayer()
        layer.store("low", importance=0.1)
        layer.store("high", importance=0.9)
        results = layer.retrieve_relevant(count=1)
        assert len(results) == 1
        assert results[0].content == "high"

    def test_retrieve_by_type(self) -> None:
        layer = MemoryLayer()
        layer.store("a", memory_type=MemoryType.SHORT_TERM)
        layer.store("b", memory_type=MemoryType.LONG_TERM)
        st = layer.retrieve_by_type(MemoryType.SHORT_TERM)
        assert len(st) == 1
        assert st[0].content == "a"

    def test_promote(self) -> None:
        layer = MemoryLayer()
        mid = layer.store("promote_me")
        assert layer.promote(mid) is True
        assert layer.get(mid).memory_type == MemoryType.LONG_TERM
        assert layer.promote("missing") is False

    def test_archive(self) -> None:
        layer = MemoryLayer()
        mid = layer.store("archive_me")
        assert layer.archive(mid) is True
        assert layer.get(mid).memory_type == MemoryType.ARCHIVED

    def test_prune(self) -> None:
        layer = MemoryLayer()
        mid = layer.store("old")
        # Manually age the memory
        layer._memories[mid].last_accessed = time.perf_counter() - 7200
        removed = layer.prune(max_age_seconds=3600)
        assert removed == 1
        assert layer.get(mid) is None

    def test_consolidate(self) -> None:
        layer = MemoryLayer()
        mid = layer.store("important", importance=0.9)
        layer._memories[mid].access_count = 10
        promoted = layer.consolidate(threshold=0.5)
        assert promoted == 1
        assert layer.get(mid).memory_type == MemoryType.LONG_TERM

    def test_enforce_short_term_limit(self) -> None:
        layer = MemoryLayer(max_short_term=2)
        layer.store("a", importance=0.1)
        layer.store("b", importance=0.2)
        layer.store("c", importance=0.3)
        st = layer.retrieve_by_type(MemoryType.SHORT_TERM)
        assert len(st) <= 2

    def test_clear(self) -> None:
        layer = MemoryLayer()
        layer.store("x")
        layer.clear()
        assert layer.count() == 0

    def test_memory_item_score(self) -> None:
        item = MemoryItem(content="test", importance=1.0)
        time.sleep(0.01)
        score = item.score()
        assert 0.0 < score <= 1.0

    def test_memory_item_touch(self) -> None:
        item = MemoryItem(content="test")
        assert item.access_count == 0
        item.touch()
        assert item.access_count == 1
