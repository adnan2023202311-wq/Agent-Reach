"""Tests for M7.2 Context Engine."""
from __future__ import annotations

import pytest

from context.engine import (
    ContextBuilder,
    ContextCompressor,
    ContextEngine,
    ContextItem,
    ContextPriority,
    ContextRanker,
    ContextWindow,
)


# ---------------------------------------------------------------------------
# ContextItem Tests
# ---------------------------------------------------------------------------


class TestContextItem:
    def test_default_creation(self) -> None:
        item = ContextItem(content="hello")
        assert item.id
        assert item.content == "hello"
        assert item.priority == ContextPriority.MEDIUM

    def test_content_hash(self) -> None:
        a = ContextItem(content="same")
        b = ContextItem(content="same")
        c = ContextItem(content="different")
        assert a.content_hash == b.content_hash
        assert a.content_hash != c.content_hash

    def test_tokens_estimate(self) -> None:
        item = ContextItem(content="hello world", tokens_estimate=3)
        assert item.tokens_estimate == 3

    def test_to_dict(self) -> None:
        item = ContextItem(content="test", priority=ContextPriority.HIGH, source="mem")
        d = item.to_dict()
        assert d["priority"] == "high"
        assert d["source"] == "mem"


# ---------------------------------------------------------------------------
# ContextRanker Tests
# ---------------------------------------------------------------------------


class TestContextRanker:
    def test_critical_scores_highest(self) -> None:
        ranker = ContextRanker()
        critical = ContextItem(content="x", priority=ContextPriority.CRITICAL)
        optional = ContextItem(content="x", priority=ContextPriority.OPTIONAL)
        assert ranker.score(critical) > ranker.score(optional)

    def test_recency_matters(self) -> None:
        ranker = ContextRanker(priority_weight=0.0, recency_weight=1.0)
        import time
        recent = ContextItem(content="x", created_at=time.time())
        old = ContextItem(content="x", created_at=0.0)
        assert ranker.score(recent) > ranker.score(old)

    def test_query_relevance(self) -> None:
        ranker = ContextRanker(priority_weight=0.0, relevance_weight=1.0)
        match = ContextItem(content="python programming language")
        no_match = ContextItem(content="javascript framework")
        assert ranker.score(match, query="python") > ranker.score(no_match, query="python")

    def test_rank_respects_limit(self) -> None:
        ranker = ContextRanker()
        items = [
            ContextItem(content=f"item_{i}", priority=list(ContextPriority)[i % len(list(ContextPriority))])
            for i in range(20)
        ]
        result = ranker.rank(items, limit=5)
        assert len(result) == 5

    def test_rank_sorted_descending(self) -> None:
        ranker = ContextRanker()
        items = [
            ContextItem(content="a", priority=ContextPriority.LOW),
            ContextItem(content="b", priority=ContextPriority.CRITICAL),
            ContextItem(content="c", priority=ContextPriority.MEDIUM),
        ]
        result = ranker.rank(items)
        scores = [ranker.score(i) for i in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# ContextBuilder Tests
# ---------------------------------------------------------------------------


class TestContextBuilder:
    def test_estimate_tokens(self) -> None:
        builder = ContextBuilder(chars_per_token=4.0)
        # 20 chars / 4 = 5 tokens
        assert builder.estimate_tokens("hello world test!!") == 4  # 19 chars / 4 = 4

    def test_add_item(self) -> None:
        builder = ContextBuilder()
        item = builder.add_item("hello", ContextPriority.HIGH, "memory")
        assert item.content == "hello"
        assert item.priority == ContextPriority.HIGH
        assert item.source == "memory"
        assert item.tokens_estimate > 0

    def test_build_window_includes_critical(self) -> None:
        builder = ContextBuilder()
        items = [
            builder.add_item("critical info", ContextPriority.CRITICAL),
            builder.add_item("optional info", ContextPriority.OPTIONAL),
        ]
        window = builder.build_window(items, budget=100)
        critical_contents = [i.content for i in window.items]
        assert "critical info" in critical_contents

    def test_build_window_respects_budget(self) -> None:
        builder = ContextBuilder(chars_per_token=1.0)
        items = [
            builder.add_item("a" * 50, ContextPriority.MEDIUM),
            builder.add_item("b" * 50, ContextPriority.MEDIUM),
        ]
        window = builder.build_window(items, budget=30)
        assert window.total_tokens <= 30

    def test_build_window_deduplicate(self) -> None:
        builder = ContextBuilder()
        items = [
            builder.add_item("duplicate", ContextPriority.MEDIUM),
            builder.add_item("duplicate", ContextPriority.MEDIUM),
            builder.add_item("unique", ContextPriority.MEDIUM),
        ]
        window = builder.build_window(items, budget=1000, deduplicate=True)
        contents = [i.content for i in window.items]
        assert contents.count("duplicate") == 1

    def test_build_window_no_dedup(self) -> None:
        builder = ContextBuilder()
        items = [
            builder.add_item("dup", ContextPriority.MEDIUM),
            builder.add_item("dup", ContextPriority.MEDIUM),
        ]
        window = builder.build_window(items, budget=1000, deduplicate=False)
        contents = [i.content for i in window.items]
        assert contents.count("dup") == 2

    def test_build_window_max_items(self) -> None:
        builder = ContextBuilder(max_context_items=3)
        items = [builder.add_item(f"item_{i}") for i in range(10)]
        window = builder.build_window(items, budget=10000)
        assert len(window.items) <= 3


# ---------------------------------------------------------------------------
# ContextCompressor Tests
# ---------------------------------------------------------------------------


class TestContextCompressor:
    def test_truncate_short_text(self) -> None:
        comp = ContextCompressor()
        result = comp.compress("short", target_tokens=100)
        assert result == "short"

    def test_truncate_long_text(self) -> None:
        comp = ContextCompressor(chars_per_token=1.0)
        text = "a" * 100
        result = comp.compress(text, target_tokens=10, strategy="truncate")
        assert len(result) <= 13  # 10 chars + "..."

    def test_summarize_strategy(self) -> None:
        comp = ContextCompressor(chars_per_token=1.0)
        text = "first line\nmiddle line\nlast line"
        result = comp.compress(text, target_tokens=40, strategy="summarize")
        assert "first" in result
        assert "last" in result

    def test_hybrid_strategy(self) -> None:
        comp = ContextCompressor(chars_per_token=4.0)
        text = "first paragraph\n" * 20
        result = comp.compress(text, target_tokens=10, strategy="hybrid")
        assert len(result) <= 45  # 10 tokens * 4 chars + ellipsis

    def test_compress_items_drops_optional(self) -> None:
        comp = ContextCompressor(chars_per_token=1.0)
        items = [
            ContextItem(content="critical", priority=ContextPriority.CRITICAL, tokens_estimate=8),
            ContextItem(content="optional", priority=ContextPriority.OPTIONAL, tokens_estimate=8),
        ]
        result = comp.compress_items(items, budget=10)
        contents = [i.content for i in result]
        assert "critical" in contents
        assert "optional" not in contents


# ---------------------------------------------------------------------------
# ContextEngine Tests
# ---------------------------------------------------------------------------


class TestContextEngine:
    def test_add_and_retrieve(self) -> None:
        engine = ContextEngine()
        cid = engine.add("test context", ContextPriority.HIGH, "test_source")
        items = engine.get_items(source="test_source")
        assert len(items) == 1
        assert items[0].id == cid

    def test_remove_item(self) -> None:
        engine = ContextEngine()
        cid = engine.add("removable")
        assert engine.remove(cid)
        assert not engine.remove("nonexistent")

    def test_get_items_filtered(self) -> None:
        engine = ContextEngine()
        engine.add("a", ContextPriority.HIGH, "s1")
        engine.add("b", ContextPriority.LOW, "s1")
        engine.add("c", ContextPriority.HIGH, "s2")
        assert len(engine.get_items(source="s1")) == 2
        assert len(engine.get_items(priority=ContextPriority.HIGH)) == 2

    def test_clear(self) -> None:
        engine = ContextEngine()
        engine.add("a", source="s1")
        engine.add("b", source="s2")
        removed = engine.clear(source="s1")
        assert removed == 1
        assert engine.item_count == 1

    def test_clear_all(self) -> None:
        engine = ContextEngine()
        engine.add("a")
        engine.add("b")
        removed = engine.clear()
        assert removed == 2
        assert engine.item_count == 0

    def test_build_returns_window(self) -> None:
        engine = ContextEngine(default_budget=1000)
        engine.add("important", ContextPriority.CRITICAL)
        window = engine.build()
        assert isinstance(window, ContextWindow)
        assert window.total_tokens > 0

    def test_build_respects_budget(self) -> None:
        engine = ContextEngine(default_budget=50, chars_per_token=1.0)
        engine.add("a" * 30, ContextPriority.CRITICAL)
        engine.add("b" * 30, ContextPriority.HIGH)
        window = engine.build()
        assert window.total_tokens <= 50

    def test_build_for_conversation(self) -> None:
        engine = ContextEngine(default_budget=2000, chars_per_token=4.0)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "how are you?"},
        ]
        window = engine.build_for_conversation(
            messages, system_prompt="Be helpful."
        )
        assert window.total_tokens > 0
        assert any("Be helpful" in i.content for i in window.items)

    def test_build_with_sources(self) -> None:
        engine = ContextEngine(default_budget=2000)
        window = engine.build_with_sources(
            system="You are helpful.",
            memories=["user likes python"],
            knowledge=["python 3.13 released"],
            conversation=[{"role": "user", "content": "latest python?"}],
        )
        assert len(window.items) >= 2
        assert any("helpful" in i.content for i in window.items)

    def test_compress_delegates(self) -> None:
        engine = ContextEngine(chars_per_token=1.0)
        result = engine.compress("a" * 100, target_tokens=10)
        assert len(result) <= 15

    def test_compress_window(self) -> None:
        engine = ContextEngine(chars_per_token=4.0)
        engine.add("a" * 80, ContextPriority.CRITICAL)
        engine.add("b" * 80, ContextPriority.MEDIUM)
        window = engine.build(budget=100)
        compressed = engine.compress_window(window, target_budget=20)
        assert compressed.total_tokens <= 20

    def test_add_items_bulk(self) -> None:
        engine = ContextEngine()
        items = [
            ContextItem(content="a"),
            ContextItem(content="b"),
        ]
        engine.add_items(items)
        assert engine.item_count == 2

    def test_get_stats(self) -> None:
        engine = ContextEngine()
        engine.add("test", ContextPriority.HIGH, "memory")
        engine.build()
        stats = engine.get_stats()
        assert "total_items" in stats
        assert "total_tokens_estimate" in stats
        assert "build_count" in stats
        assert stats["build_count"] == 1


# ---------------------------------------------------------------------------
# ContextWindow Tests
# ---------------------------------------------------------------------------


class TestContextWindow:
    def test_to_text(self) -> None:
        window = ContextWindow(
            items=[
                ContextItem(content="first"),
                ContextItem(content="second"),
            ],
            total_tokens=10,
            budget=100,
            usage_pct=10.0,
        )
        text = window.to_text()
        assert "first" in text
        assert "second" in text

    def test_to_messages(self) -> None:
        window = ContextWindow(
            items=[
                ContextItem(content="sys msg"),
                ContextItem(content="ctx msg"),
            ],
        )
        messages = window.to_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "sys msg"
