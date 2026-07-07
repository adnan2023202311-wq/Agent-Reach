"""Tests for M7.1 LongCat Memory Engine."""
from __future__ import annotations

import pytest
import time

from memory.layer import MemoryType
from memory.longcat import (
    CompressedMemory,
    CompressedMemoryType,
    LongCatMemoryEngine,
    MemoryGraphNode,
    MemoryRanker,
    MemorySnapshot,
    SemanticMemorySearch,
)


class TestMemoryRanker:
    def test_ranker_scores_higher_for_important_memory(self) -> None:
        from memory.layer import MemoryItem
        ranker = MemoryRanker()
        hi = MemoryItem(content="important", importance=0.9)
        lo = MemoryItem(content="unimportant", importance=0.1)
        assert ranker.score(hi) > ranker.score(lo)

    def test_ranker_scores_higher_for_recent_memory(self) -> None:
        from memory.layer import MemoryItem
        ranker = MemoryRanker()
        recent = MemoryItem(content="recent", last_accessed=time.time())
        old = MemoryItem(content="old", last_accessed=0.0)
        assert ranker.score(recent) > ranker.score(old)

    def test_ranker_scores_higher_for_query_match(self) -> None:
        from memory.layer import MemoryItem
        ranker = MemoryRanker()
        matching = MemoryItem(content="the quick brown fox", importance=0.5)
        non_matching = MemoryItem(content="lorem ipsum dolor", importance=0.5)
        assert ranker.score(matching, query="fox") > ranker.score(non_matching, query="fox")

    def test_rank_returns_limited_results(self) -> None:
        from memory.layer import MemoryItem
        ranker = MemoryRanker()
        memories = [MemoryItem(content=f"memory_{i}", importance=0.1 * i) for i in range(20)]
        result = ranker.rank(memories, limit=5)
        assert len(result) == 5

    def test_rank_sorted_by_score(self) -> None:
        from memory.layer import MemoryItem
        ranker = MemoryRanker()
        memories = [MemoryItem(content=f"memory_{i}", importance=0.1 * i) for i in range(5)]
        result = ranker.rank(memories)
        scores = [ranker.score(m) for m in result]
        assert scores == sorted(scores, reverse=True)


class TestSemanticMemorySearch:
    def test_index_and_search(self) -> None:
        search = SemanticMemorySearch()
        search.index("m1", "the quick brown fox jumps over the lazy dog")
        search.index("m2", "machine learning is a subset of artificial intelligence")
        search.index("m3", "foxes are clever animals")
        results = search.search("fox")
        ids = [r[0] for r in results]
        assert "m1" in ids or "m3" in ids

    def test_search_no_match(self) -> None:
        search = SemanticMemorySearch()
        search.index("m1", "python programming language")
        results = search.search("quantum")
        assert len(results) == 0

    def test_deindex_removes_memory(self) -> None:
        search = SemanticMemorySearch()
        search.index("m1", "hello world")
        search.index("m2", "hello universe")
        search.deindex("m1")
        results = search.search("hello")
        ids = [r[0] for r in results]
        assert "m1" not in ids
        assert "m2" in ids

    def test_clear_removes_all(self) -> None:
        search = SemanticMemorySearch()
        search.index("m1", "test content")
        search.clear()
        results = search.search("test")
        assert len(results) == 0

    def test_tokenize_handles_unicode(self) -> None:
        tokens = SemanticMemorySearch._tokenize("hello мир 世界 test123")
        assert "hello" in tokens
        assert "мир" in tokens
        assert "test123" in tokens

    def test_search_with_candidate_filter(self) -> None:
        search = SemanticMemorySearch()
        search.index("m1", "python programming")
        search.index("m2", "python development")
        results = search.search("python", candidate_ids={"m1"})
        assert len(results) == 1
        assert results[0][0] == "m1"


class TestLongCatMemoryEngine:
    def test_store_and_retrieve(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("Hello World", importance=0.8)
        mem = engine.get(mid)
        assert mem is not None
        assert mem.content == "Hello World"
        assert mem.importance == 0.8

    def test_store_adds_to_working_memory(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("test", add_to_working=True)
        working = engine.working_memory
        assert len(working) > 0
        assert any(m.id == mid for m in working)

    def test_store_without_working_memory(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("test", add_to_working=False)
        assert len(engine.working_memory) == 0

    def test_retrieve_relevant(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("python", importance=0.9)
        engine.store("java", importance=0.5)
        engine.store("golang", importance=0.7)
        results = engine.retrieve_relevant(count=2)
        assert len(results) == 2
        assert results[0].content == "python"

    def test_semantic_search(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("machine learning with python")
        engine.store("web development with javascript")
        engine.store("data science with python")
        results = engine.semantic_search("python", limit=2)
        assert len(results) > 0

    def test_working_memory_limit(self) -> None:
        engine = LongCatMemoryEngine(working_memory_size=3)
        for i in range(10):
            engine.store(f"memory_{i}")
        assert len(engine.working_memory) == 3

    def test_get_working_context(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("first")
        engine.store("second")
        ctx = engine.get_working_context(max_items=2)
        assert len(ctx) <= 2

    def test_clear_working_memory(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("test")
        engine.clear_working_memory()
        assert len(engine.working_memory) == 0

    def test_set_working_memory(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("a")
        m2 = engine.store("b")
        engine.clear_working_memory()
        engine.set_working_memory([m1, m2])
        working_ids = {m.id for m in engine.working_memory}
        assert m1 in working_ids
        assert m2 in working_ids

    def test_consolidation(self) -> None:
        engine = LongCatMemoryEngine()
        for i in range(5):
            engine.store(f"important_{i}", importance=0.9)
        count = engine.consolidate(threshold=0.5)
        assert engine.get_consolidation_count() >= 1

    def test_compress_conversation(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [
            engine.store("Hello, how are you?"),
            engine.store("I'm doing well, thanks!"),
            engine.store("What can I help with?"),
        ]
        cid = engine.compress_conversation(ids)
        compressed = engine.get_compressed(cid)
        assert compressed is not None
        assert compressed.compression_type == CompressedMemoryType.CONVERSATION
        assert len(compressed.source_ids) == 3

    def test_compress_project(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [engine.store(f"task_{i}") for i in range(3)]
        cid = engine.compress_project(ids, "MyProject")
        compressed = engine.get_compressed(cid)
        assert compressed is not None
        assert compressed.compression_type == CompressedMemoryType.PROJECT
        assert "MyProject" in compressed.summary

    def test_expand_compressed(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [engine.store(f"msg_{i}") for i in range(3)]
        cid = engine.compress_conversation(ids)
        expanded = engine.expand_compressed(cid)
        assert len(expanded) == 3

    def test_list_compressed_by_type(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [engine.store("x") for _ in range(2)]
        engine.compress_conversation(ids)
        engine.compress_project(ids, "P")
        assert len(engine.list_compressed(CompressedMemoryType.CONVERSATION)) == 1
        assert len(engine.list_compressed(CompressedMemoryType.PROJECT)) == 1

    def test_snapshots(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("apple")
        m2 = engine.store("banana")
        m3 = engine.store("cherry")
        sid = engine.create_snapshot(label="fruits", memory_ids=[m1, m2, m3])
        snapshot = engine.get_snapshot(sid)
        assert snapshot is not None
        assert snapshot.label == "fruits"
        assert len(snapshot.memory_ids) == 3

    def test_snapshot_versioning(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("v1")
        sid1 = engine.create_snapshot(label="test")
        m2 = engine.store("v2")
        sid2 = engine.create_snapshot(label="test")
        s1 = engine.get_snapshot(sid1)
        s2 = engine.get_snapshot(sid2)
        assert s1 is not None and s2 is not None
        assert s2.version > s1.version

    def test_restore_snapshot(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("keep")
        m2 = engine.store("also_keep")
        sid = engine.create_snapshot(memory_ids=[m1, m2])
        engine.clear_working_memory()
        restored = engine.restore_snapshot(sid)
        assert len(restored) == 2
        assert len(engine.working_memory) == 2

    def test_replay_chronological(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [engine.store(f"step_{i}") for i in range(5)]
        time.sleep(0.01)
        replayed = engine.replay(ids, chronological=True)
        assert len(replayed) == 5
        for i in range(len(replayed) - 1):
            assert replayed[i].created_at <= replayed[i + 1].created_at

    def test_replay_session(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("s1_msg1", metadata={"session_id": "s1"})
        engine.store("s1_msg2", metadata={"session_id": "s1"})
        engine.store("s2_msg1", metadata={"session_id": "s2"})
        items = engine.replay_session("s1")
        assert len(items) == 2
        assert all(m.metadata.get("session_id") == "s1" for m in items)

    def test_link_memories(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("source")
        m2 = engine.store("target")
        engine.link_memories(m1, m2, "depends_on")
        related = engine.get_related(m1, depth=1)
        assert len(related) == 1
        assert related[0][1] == "depends_on"

    def test_get_related_filtered_by_relationship(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("a")
        m2 = engine.store("b")
        m3 = engine.store("c")
        engine.link_memories(m1, m2, "uses")
        engine.link_memories(m1, m3, "requires")
        related = engine.get_related(m1, relationship="uses")
        assert len(related) == 1
        assert related[0][1] == "uses"

    def test_get_related_depth(self) -> None:
        engine = LongCatMemoryEngine()
        a = engine.store("a")
        b = engine.store("b")
        c = engine.store("c")
        engine.link_memories(a, b, "depends_on")
        engine.link_memories(b, c, "depends_on")
        related1 = engine.get_related(a, depth=1)
        assert len(related1) == 1
        related2 = engine.get_related(a, depth=2)
        assert len(related2) == 2

    def test_graph_stats(self) -> None:
        engine = LongCatMemoryEngine()
        m1 = engine.store("a")
        m2 = engine.store("b")
        engine.link_memories(m1, m2, "depends_on")
        stats = engine.get_graph_stats()
        assert stats["nodes"] >= 1
        assert stats["edges"] >= 1

    def test_prune(self) -> None:
        engine = LongCatMemoryEngine(working_memory_size=5)
        mid = engine.store("old", importance=0.0)
        engine._layer._memories[mid].last_accessed = 0.0
        count = engine.prune(max_age_seconds=0.0, min_importance=0.0)
        assert count >= 0

    def test_summarize_memories(self) -> None:
        engine = LongCatMemoryEngine()
        ids = [engine.store(f"line_{i}") for i in range(10)]
        summary = engine.summarize_memories(ids, max_length=200)
        assert len(summary) <= 200
        assert summary

    def test_context_window(self) -> None:
        engine = LongCatMemoryEngine()
        for i in range(20):
            engine.store(f"memory content number {i}", importance=0.5)
        window = engine.get_context_window(max_tokens=100, chars_per_token=4.0)
        total_chars = sum(len(str(c)) for c in window)
        assert total_chars <= 400

    def test_compress_context(self) -> None:
        engine = LongCatMemoryEngine()
        context = [f"long content line {i}" for i in range(100)]
        compressed = engine.compress_context(context, target_tokens=50)
        assert len(compressed) <= 200

    def test_expand_context(self) -> None:
        engine = LongCatMemoryEngine()
        compressed = engine.compress_context(["a", "b", "c"], target_tokens=500)
        level1 = engine.expand_context(compressed, detail_level=1)
        level2 = engine.expand_context(compressed, detail_level=2)
        assert level1 is not None
        assert level2 is not None

    def test_get_stats(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("test1", importance=0.8)
        engine.store("test2", importance=0.5)
        engine.consolidate(threshold=0.6)
        ids = list(engine._layer._memories.keys())
        engine.compress_conversation(ids)
        engine.create_snapshot(label="stats_test")
        engine.link_memories(ids[0], ids[1], "depends_on")
        stats = engine.get_stats()
        assert "memory_counts" in stats
        assert "memory_graph" in stats
        assert "consolidation_count" in stats
        assert "avg_importance" in stats
        assert stats["memory_counts"]["total"] >= 2

    def test_clear(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("test")
        engine.create_snapshot()
        ids = list(engine._layer._memories.keys())
        engine.compress_conversation(ids)
        engine.clear()
        assert len(engine.working_memory) == 0
        assert len(engine._layer._memories) == 0
        assert len(engine._compressed) == 0
        assert len(engine._snapshots) == 0


class TestMemorySnapshot:
    def test_to_dict(self) -> None:
        snapshot = MemorySnapshot(label="test", memory_ids=["a", "b"], summary="summary")
        d = snapshot.to_dict()
        assert d["label"] == "test"
        assert d["memory_ids"] == ["a", "b"]

    def test_default_values(self) -> None:
        snapshot = MemorySnapshot()
        assert snapshot.id
        assert snapshot.version == 1
        assert snapshot.memory_ids == []


class TestCompressedMemory:
    def test_to_dict(self) -> None:
        cm = CompressedMemory(
            compression_type=CompressedMemoryType.CONVERSATION,
            source_ids=["a", "b"],
            summary="test summary",
        )
        d = cm.to_dict()
        assert d["compression_type"] == "conversation"
        assert d["source_ids"] == ["a", "b"]

    def test_default_values(self) -> None:
        cm = CompressedMemory()
        assert cm.compression_type == CompressedMemoryType.CONVERSATION
        assert cm.importance == 0.5
        assert cm.version == 1


class TestMemoryGraphNode:
    def test_creation(self) -> None:
        node = MemoryGraphNode(memory_id="m1", weight=0.8)
        assert node.memory_id == "m1"
        assert node.weight == 0.8
        assert node.edges == {}

    def test_edges(self) -> None:
        node = MemoryGraphNode(memory_id="m1")
        node.edges["m2"] = "depends_on"
        node.edges["m3"] = "related_to"
        assert len(node.edges) == 2
