"""Tests for M9.17 — Intelligent Auto Integration.

Proves: curated mappings for the spec-named technologies, capability
keyword analysis for unknown ones, live-object analysis via the M9.26
validator, scaffold generation that is REAL parseable Python
implementing the category contract (validated statically, never
executed server-side), mapped-delegation scaffolds passing the
registry validator end-to-end, and the API.
"""

from __future__ import annotations

import ast

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings
from infrastructure.adapters import AdapterRegistry
from infrastructure.auto_integration import (
    AutoIntegrationEngine,
    generate_adapter_scaffold,
    validate_scaffold,
)


def _engine() -> AutoIntegrationEngine:
    return AutoIntegrationEngine(AdapterRegistry(build_intelligent_pipeline()))


# ===========================================================================
# Analysis
# ===========================================================================


class TestAnalysis:
    def test_curated_technologies(self) -> None:
        engine = _engine()
        report = engine.analyze("LongCat")
        assert report.payload["basis"] == "curated"
        assert report.payload["candidate_categories"] == ["memory"]
        contract = report.payload["contracts"]["memory"]
        names = {m["name"] for m in contract["required_interface"]}
        assert {"store", "retrieve_relevant", "get_stats", "clear"} == names

    def test_moa_and_agent_skills_curated(self) -> None:
        engine = _engine()
        assert engine.analyze("MOA").payload["candidate_categories"] == ["plugin"]
        skills = engine.analyze("Agent Skills").payload
        assert set(skills["candidate_categories"]) == {"plugin", "tool"}

    def test_unknown_technology_from_capabilities(self) -> None:
        engine = _engine()
        report = engine.analyze(
            "HyperMem", capabilities=["long-term memory storage", "vector retrieval"]
        )
        assert report.payload["basis"] == "declared_capabilities"
        assert "memory" in report.payload["candidate_categories"]

    def test_unknown_without_capabilities_honest(self) -> None:
        engine = _engine()
        report = engine.analyze("MysteryTech")
        assert report.payload["candidate_categories"] == []
        assert "No declared capability" in report.payload["note"]

    def test_live_object_analysis_uses_registry_validator(self) -> None:
        class _MemoryLike:
            def store(self, *a, **k): ...
            def retrieve_relevant(self, *a, **k): ...
            def get_stats(self): ...
            def clear(self): ...

        engine = _engine()
        report = engine.analyze_object("MemLike", _MemoryLike())
        assert "memory" in report.payload["compatible_categories"]
        assert "tool" in report.payload["problems_by_category"]

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            _engine().analyze("  ")


# ===========================================================================
# Generation & validation
# ===========================================================================


class TestGeneration:
    def test_scaffold_is_real_parseable_python(self) -> None:
        source = generate_adapter_scaffold("memory", "HyperMem")
        tree = ast.parse(source)  # must not raise
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert classes[0].name == "HypermemMemoryAdapter"
        assert validate_scaffold("memory", source) == []

    def test_async_contract_respected(self) -> None:
        source = generate_adapter_scaffold("provider", "FastLLM")
        tree = ast.parse(source)
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        complete = next(
            n for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "complete"
        )
        assert isinstance(complete, ast.AsyncFunctionDef)

    def test_unmapped_methods_raise_not_implemented(self) -> None:
        source = generate_adapter_scaffold("memory", "HyperMem")
        assert "NotImplementedError" in source

    def test_mapped_scaffold_passes_registry_validation_end_to_end(self) -> None:
        """A fully mapped generated adapter, executed in a TEST
        namespace (never by the server), satisfies the registry."""
        source = generate_adapter_scaffold(
            "memory",
            "HyperMem",
            target_methods={
                "store": "save",
                "retrieve_relevant": "query",
                "get_stats": "stats",
                "clear": "reset",
            },
        )
        namespace: dict = {}
        exec(compile(source, "<generated>", "exec"), namespace)  # test-only
        adapter_cls = namespace["HypermemMemoryAdapter"]

        class _Target:
            def save(self, *a, **k): return "id"
            def query(self, *a, **k): return []
            def stats(self): return {}
            def reset(self): return None

        registry = AdapterRegistry(build_intelligent_pipeline())
        registered = registry.register("memory", "hypermem", adapter_cls(_Target()))
        assert registered.category == "memory"

    def test_unknown_category_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_adapter_scaffold("teleporter", "X")

    def test_validate_scaffold_catches_problems(self) -> None:
        missing = "class X:\n    def store(self):\n        pass\n"
        problems = validate_scaffold("memory", missing)
        assert any("retrieve_relevant" in p for p in problems)
        assert validate_scaffold("memory", "def broken(:")[0].startswith("SyntaxError")
        assert validate_scaffold("memory", "x = 1") == ["No class definition found"]

    def test_reports_persisted(self) -> None:
        engine = _engine()
        analysis = engine.analyze("LongCat")
        generation = engine.generate("LongCat", "memory")
        reports = engine.list_reports()
        assert [r.report_id for r in reports] == [
            generation.report_id, analysis.report_id,
        ]
        assert engine.get_report(analysis.report_id) is analysis


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


class TestAutoIntegrationAPI:
    def test_analyze_endpoint(self, client: TestClient) -> None:
        report = client.post(
            "/api/v1/auto-integration/analyze", json={"technology": "LongCat"}
        ).json()
        assert report["payload"]["candidate_categories"] == ["memory"]

    def test_generate_and_validate_flow(self, client: TestClient) -> None:
        generated = client.post(
            "/api/v1/auto-integration/generate",
            json={"technology": "HyperMem", "category": "memory"},
        ).json()
        assert generated["payload"]["valid"] is True
        assert "never executes it" in generated["payload"]["note"]

        validation = client.post(
            "/api/v1/auto-integration/validate",
            json={"category": "memory", "source": generated["payload"]["source"]},
        ).json()
        assert validation["valid"] is True

    def test_generate_unknown_category_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auto-integration/generate",
            json={"technology": "X", "category": "teleporter"},
        )
        assert resp.status_code == 422

    def test_reports_endpoints(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/auto-integration/analyze", json={"technology": "MOA"}
        ).json()
        listing = client.get("/api/v1/auto-integration/reports").json()
        assert listing["count"] >= 1
        detail = client.get(
            f"/api/v1/auto-integration/reports/{created['report_id']}"
        )
        assert detail.status_code == 200
        assert (
            client.get("/api/v1/auto-integration/reports/ghost").status_code
            == 404
        )
