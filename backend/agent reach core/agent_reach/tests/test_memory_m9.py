"""Tests for M9.7 — Runtime Memory (LongCat extensions).

Covers the new engine operations — browse, delete, pin/unpin, merge —
plus their interaction with pruning/limit enforcement, and the new
/api/v1/memory endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from memory.layer import MemoryType
from memory.longcat import LongCatMemoryEngine


# ===========================================================================
# Engine: browse
# ===========================================================================


class TestBrowse:
    def test_browse_newest_first(self) -> None:
        engine = LongCatMemoryEngine()
        first = engine.store("first")
        second = engine.store("second")
        items = engine.browse()
        assert [m.id for m in items[:2]] == [second, first]

    def test_browse_pagination(self) -> None:
        engine = LongCatMemoryEngine()
        for i in range(10):
            engine.store(f"memory {i}")
        page1 = engine.browse(offset=0, limit=4)
        page2 = engine.browse(offset=4, limit=4)
        assert len(page1) == 4
        assert len(page2) == 4
        assert {m.id for m in page1}.isdisjoint({m.id for m in page2})

    def test_browse_filters_by_type(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("short one")
        lt = engine.store("long one", memory_type=MemoryType.LONG_TERM)
        items = engine.browse(memory_type=MemoryType.LONG_TERM)
        assert [m.id for m in items] == [lt]

    def test_browse_does_not_touch_access_stats(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("untouched")
        engine.browse()
        assert engine._layer._memories[mid].access_count == 0

    def test_browse_pinned_only(self) -> None:
        engine = LongCatMemoryEngine()
        engine.store("normal")
        pinned = engine.store("pinned")
        engine.pin(pinned)
        items = engine.browse(pinned_only=True)
        assert [m.id for m in items] == [pinned]


# ===========================================================================
# Engine: delete
# ===========================================================================


class TestDelete:
    def test_delete_removes_everywhere(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("to be deleted", add_to_working=True)
        other = engine.store("stays")
        engine.link_memories(other, mid, "related")
        engine.pin(mid)

        assert engine.delete(mid) is True
        assert engine.get(mid) is None
        assert mid not in [m.id for m in engine.working_memory]
        assert not engine.is_pinned(mid)
        # graph edges pointing at the deleted memory are gone
        assert all(mid not in node.edges for node in engine._graph.values())
        # search index no longer returns it
        assert all(m.id != mid for m, _ in engine.semantic_search("deleted"))

    def test_delete_unknown_returns_false(self) -> None:
        engine = LongCatMemoryEngine()
        assert engine.delete("ghost") is False


# ===========================================================================
# Engine: pin
# ===========================================================================


class TestPin:
    def test_pin_unpin_roundtrip(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("important")
        assert engine.pin(mid) is True
        assert engine.is_pinned(mid) is True
        assert engine.unpin(mid) is True
        assert engine.is_pinned(mid) is False

    def test_pin_unknown_returns_false(self) -> None:
        engine = LongCatMemoryEngine()
        assert engine.pin("ghost") is False

    def test_unpin_not_pinned_returns_false(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("x")
        assert engine.unpin(mid) is False

    def test_pinned_memory_survives_prune(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("keep me")
        engine.pin(mid)
        # max_age_seconds=0 would prune everything unpinned
        engine.prune(max_age_seconds=0.0)
        assert engine.get(mid) is not None

    def test_pinned_memory_survives_limit_enforcement(self) -> None:
        engine = LongCatMemoryEngine(max_short_term=5)
        pinned = engine.store("pinned", importance=0.0)
        engine.pin(pinned)
        for i in range(20):
            engine.store(f"filler {i}", importance=0.9)
        item = engine._layer._memories[pinned]
        assert item.memory_type == MemoryType.SHORT_TERM

    def test_stats_report_pinned_count(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("x")
        engine.pin(mid)
        assert engine.get_stats()["pinned"] == 1

    def test_clear_resets_pins(self) -> None:
        engine = LongCatMemoryEngine()
        mid = engine.store("x")
        engine.pin(mid)
        engine.clear()
        assert engine.pinned_ids == set()


# ===========================================================================
# Engine: merge
# ===========================================================================


class TestMerge:
    def test_merge_combines_and_deletes_sources(self) -> None:
        engine = LongCatMemoryEngine()
        a = engine.store("alpha", importance=0.3, metadata={"k1": "v1"})
        b = engine.store("beta", importance=0.8, metadata={"k2": "v2"})
        merged_id = engine.merge([a, b])
        assert merged_id is not None
        merged = engine._layer._memories[merged_id]
        assert "alpha" in str(merged.content) and "beta" in str(merged.content)
        assert merged.importance == 0.8
        assert merged.metadata["k1"] == "v1" and merged.metadata["k2"] == "v2"
        assert merged.metadata["merged_from"] == [a, b]
        assert engine.get(a) is None and engine.get(b) is None

    def test_merge_preserves_pin(self) -> None:
        engine = LongCatMemoryEngine()
        a = engine.store("a")
        b = engine.store("b")
        engine.pin(a)
        merged_id = engine.merge([a, b])
        assert engine.is_pinned(merged_id)

    def test_merge_requires_two_existing(self) -> None:
        engine = LongCatMemoryEngine()
        a = engine.store("only one")
        assert engine.merge([a, "ghost"]) is None
        assert engine.merge(["g1", "g2"]) is None
        # nothing was deleted on the failed path
        assert engine.get(a) is not None

    def test_merged_memory_is_searchable(self) -> None:
        engine = LongCatMemoryEngine()
        a = engine.store("quantum entanglement basics")
        b = engine.store("superposition principles")
        merged_id = engine.merge([a, b])
        hits = [m.id for m, _ in engine.semantic_search("quantum superposition")]
        assert merged_id in hits


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


def _store(client: TestClient, content: str) -> str:
    resp = client.post("/api/v1/memory/store", json={"content": content})
    assert resp.status_code == 200
    return resp.json()["id"]


class TestMemoryAPI:
    def test_browse_endpoint(self, client: TestClient) -> None:
        _store(client, "browse target")
        resp = client.get("/api/v1/memory/browse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert any("browse target" in i["content"] for i in data["items"])

    def test_browse_invalid_type_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/memory/browse?memory_type=eternal")
        assert resp.status_code == 422

    def test_pin_unpin_endpoints(self, client: TestClient) -> None:
        mid = _store(client, "pin me")
        assert client.post(f"/api/v1/memory/{mid}/pin").json()["pinned"] is True
        browse = client.get("/api/v1/memory/browse?pinned_only=true").json()
        assert any(i["id"] == mid for i in browse["items"])
        assert client.delete(f"/api/v1/memory/{mid}/pin").json()["pinned"] is False

    def test_pin_unknown_404(self, client: TestClient) -> None:
        assert client.post("/api/v1/memory/ghost/pin").status_code == 404

    def test_delete_endpoint(self, client: TestClient) -> None:
        mid = _store(client, "delete me")
        assert client.delete(f"/api/v1/memory/{mid}").json()["status"] == "deleted"
        assert client.delete(f"/api/v1/memory/{mid}").status_code == 404

    def test_merge_endpoint(self, client: TestClient) -> None:
        a = _store(client, "merge part one")
        b = _store(client, "merge part two")
        resp = client.post(
            "/api/v1/memory/merge", json={"memory_ids": [a, b]}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "merged"

    def test_merge_insufficient_sources_422(self, client: TestClient) -> None:
        a = _store(client, "lonely")
        resp = client.post(
            "/api/v1/memory/merge", json={"memory_ids": [a, "ghost"]}
        )
        assert resp.status_code == 422

    def test_summarize_endpoint(self, client: TestClient) -> None:
        a = _store(client, "summarize alpha content")
        b = _store(client, "summarize beta content")
        resp = client.post(
            "/api/v1/memory/summarize", json={"memory_ids": [a, b]}
        )
        assert resp.status_code == 200
        assert resp.json()["summary"]

    def test_semantic_search_endpoint(self, client: TestClient) -> None:
        _store(client, "the quick brown fox jumps")
        resp = client.post(
            "/api/v1/memory/semantic-search",
            json={"query": "quick fox", "count": 5},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert all("score" in i for i in items)

    def test_clear_still_works(self, client: TestClient) -> None:
        """Backward compatibility: /clear must not be shadowed by
        the new /{memory_id} delete route."""
        _store(client, "soon gone")
        resp = client.delete("/api/v1/memory/clear")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
