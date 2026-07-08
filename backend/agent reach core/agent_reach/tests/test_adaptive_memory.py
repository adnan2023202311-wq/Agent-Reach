"""Tests for M9.21 — Adaptive Memory Evolution.

Proves: policy-driven two-phase forgetting (archive → delete) with
pinned exemption at both phases, revival detection, consolidation and
session compression through the engine's existing primitives, honest
before/after reports, policy validation, and the /api/v1/memory/
adaptive endpoints.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from memory.adaptive import AdaptiveMemoryManager, MemoryPolicy
from memory.layer import MemoryType
from memory.longcat import LongCatMemoryEngine


def _aged(engine: LongCatMemoryEngine, memory_id: str, seconds: float) -> None:
    """Backdate a memory's last access (perf_counter clock)."""
    engine._layer._memories[memory_id].last_accessed = (
        time.perf_counter() - seconds
    )


def _instant_policy(**overrides) -> MemoryPolicy:
    defaults = dict(
        archive_age_seconds=0.0,
        archive_max_importance=0.4,
        archive_max_access_count=2,
        delete_after_archived_seconds=0.0,
    )
    defaults.update(overrides)
    return MemoryPolicy(**defaults)


# ===========================================================================
# Forgetting
# ===========================================================================


class TestForgetting:
    def test_archive_respects_all_policy_gates(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(
            engine, MemoryPolicy(archive_age_seconds=100.0)
        )
        old_low = engine.store("old unimportant", importance=0.2, add_to_working=False)
        old_high = engine.store("old important", importance=0.9, add_to_working=False)
        fresh_low = engine.store("fresh unimportant", importance=0.2, add_to_working=False)
        _aged(engine, old_low, 200.0)
        _aged(engine, old_high, 200.0)

        archived, deleted = manager.forget()
        assert archived == 1
        assert deleted == 0
        assert engine._layer._memories[old_low].memory_type == MemoryType.ARCHIVED
        assert engine._layer._memories[old_high].memory_type == MemoryType.SHORT_TERM
        assert engine._layer._memories[fresh_low].memory_type == MemoryType.SHORT_TERM

    def test_frequently_accessed_not_archived(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(engine, _instant_policy(
            delete_after_archived_seconds=9999.0
        ))
        popular = engine.store("popular", importance=0.1, add_to_working=False)
        engine._layer._memories[popular].access_count = 10
        _aged(engine, popular, 100.0)
        archived, _ = manager.forget()
        assert archived == 0

    def test_pinned_never_archived_or_deleted(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(engine, _instant_policy())
        pinned = engine.store("precious", importance=0.0, add_to_working=False)
        engine.pin(pinned)
        _aged(engine, pinned, 9999.0)
        archived, deleted = manager.forget()
        assert archived == 0 and deleted == 0
        assert engine.get(pinned) is not None

    def test_two_phase_archive_then_delete(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(engine, _instant_policy())
        doomed = engine.store("doomed", importance=0.1, add_to_working=False)
        _aged(engine, doomed, 100.0)

        archived, deleted = manager.forget()  # phase 1 archives
        assert (archived, deleted) == (1, 0)
        # retention window is 0 → next pass deletes
        archived2, deleted2 = manager.forget()
        assert (archived2, deleted2) == (0, 1)
        assert engine.get(doomed) is None
        # deletion went through the real engine path — index cleaned
        assert all(m.id != doomed for m, _ in engine.semantic_search("doomed"))

    def test_revived_memory_stops_being_tracked(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(engine, _instant_policy())
        memory_id = engine.store("revivable", importance=0.1, add_to_working=False)
        _aged(engine, memory_id, 100.0)
        manager.forget()  # archived
        engine._layer._memories[memory_id].memory_type = MemoryType.LONG_TERM  # revived
        _, deleted = manager.forget()
        assert deleted == 0
        assert memory_id not in manager._archived_at

    def test_retention_window_respected(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(
            engine, _instant_policy(delete_after_archived_seconds=9999.0)
        )
        memory_id = engine.store("kept archived", importance=0.1, add_to_working=False)
        _aged(engine, memory_id, 100.0)
        manager.forget()
        _, deleted = manager.forget()
        assert deleted == 0
        assert engine.get(memory_id) is not None


# ===========================================================================
# optimize()
# ===========================================================================


class TestOptimize:
    def test_full_pass_reports_real_counts(self) -> None:
        engine = LongCatMemoryEngine()
        manager = AdaptiveMemoryManager(engine, _instant_policy(
            delete_after_archived_seconds=9999.0,
            compress_session_min_items=3,
        ))
        # consolidation candidates (high importance short-term)
        for i in range(3):
            engine.store(f"valuable {i}", importance=0.95, add_to_working=False)
        # forgetting candidates
        stale = engine.store("stale", importance=0.1, add_to_working=False)
        _aged(engine, stale, 100.0)
        # a crowded session
        for i in range(3):
            engine.store(
                f"chat {i}", importance=0.6,
                metadata={"session_id": "s1"}, add_to_working=False,
            )

        report = manager.optimize()
        assert report.consolidated >= 3
        assert report.archived == 1
        assert report.compressed_sessions == ["s1"]
        assert report.before["total"] == 7
        assert report.after["compressed"] == 1
        assert manager.get_reports()[0] is report

    def test_empty_engine_honest_report(self) -> None:
        manager = AdaptiveMemoryManager(LongCatMemoryEngine())
        report = manager.optimize()
        assert report.consolidated == 0
        assert report.archived == 0
        assert report.deleted == 0
        assert report.compressed_sessions == []

    def test_policy_validation(self) -> None:
        engine = LongCatMemoryEngine()
        with pytest.raises(ValueError):
            AdaptiveMemoryManager(engine, MemoryPolicy(archive_max_importance=2.0))
        with pytest.raises(ValueError):
            AdaptiveMemoryManager(engine, MemoryPolicy(archive_age_seconds=-1.0))


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


class TestAdaptiveMemoryAPI:
    def test_status_shows_policy_and_live_counts(self, client: TestClient) -> None:
        status = client.get("/api/v1/memory/adaptive/status").json()
        assert "archive_age_seconds" in status["policy"]
        assert status["total_passes"] == 0
        assert status["memory_counts"]["total"] == 0

    def test_manager_operates_on_shared_engine(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "remember this exchange"})
        status = client.get("/api/v1/memory/adaptive/status").json()
        # chat stored memories in the pipeline's engine — the adaptive
        # manager sees the same instance.
        assert status["memory_counts"]["total"] >= 1

    def test_optimize_endpoint_and_reports(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "some memory traffic"})
        report = client.post("/api/v1/memory/adaptive/optimize").json()
        assert "before" in report and "after" in report
        reports = client.get("/api/v1/memory/adaptive/reports").json()
        assert reports["count"] == 1
