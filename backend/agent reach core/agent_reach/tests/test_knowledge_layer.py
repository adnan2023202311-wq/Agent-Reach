"""Tests for Knowledge Layer (M4.6)."""

from __future__ import annotations

import pytest

from knowledge.layer import KnowledgeEntry, KnowledgeLayer


class TestKnowledgeLayer:
    def test_add_and_get(self) -> None:
        layer = KnowledgeLayer()
        entry = KnowledgeEntry(content="hello world")
        entry_id = layer.add(entry)
        retrieved = layer.get(entry_id)
        assert retrieved is not None
        assert retrieved.content == "hello world"

    def test_add_text_convenience(self) -> None:
        layer = KnowledgeLayer()
        entry_id = layer.add_text("quick fox", source="test", tags=["animal"])
        entry = layer.get(entry_id)
        assert entry.content == "quick fox"
        assert entry.source == "test"
        assert entry.tags == ["animal"]

    def test_remove(self) -> None:
        layer = KnowledgeLayer()
        entry_id = layer.add_text("tmp")
        assert layer.remove(entry_id) is True
        assert layer.get(entry_id) is None
        assert layer.remove("missing") is False

    def test_search(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("The quick brown fox")
        layer.add_text("Lazy dog sleeping")
        layer.add_text("Quick thinking agent")
        results = layer.search("quick")
        assert len(results) == 2

    def test_search_case_insensitive(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("HELLO")
        results = layer.search("hello")
        assert len(results) == 1

    def test_search_by_tag(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("A", tags=["x", "y"])
        layer.add_text("B", tags=["y"])
        layer.add_text("C", tags=["z"])
        results = layer.search_by_tag("y")
        assert len(results) == 2

    def test_search_by_source(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("A", source="src1")
        layer.add_text("B", source="src2")
        layer.add_text("C", source="src1")
        results = layer.search_by_source("src1")
        assert len(results) == 2

    def test_list_all(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("A")
        layer.add_text("B")
        assert len(layer.list_all()) == 2

    def test_count(self) -> None:
        layer = KnowledgeLayer()
        assert layer.count() == 0
        layer.add_text("A")
        assert layer.count() == 1

    def test_clear(self) -> None:
        layer = KnowledgeLayer()
        layer.add_text("A")
        layer.clear()
        assert layer.count() == 0

    def test_entry_metadata(self) -> None:
        entry = KnowledgeEntry(content="data", metadata={"key": "value"})
        assert entry.metadata["key"] == "value"
