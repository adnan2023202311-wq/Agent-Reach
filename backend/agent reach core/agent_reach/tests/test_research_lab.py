"""Tests for M9.28 — AI Research Laboratory.

Proves: strict experiment validation (≥2 variants, known kinds,
PipelineConfig field checking), controlled execution — identical
task lists per variant, real measurements (pipeline traces, prompt
renders, memory optimize reports) — metric-declared winner
selection, failure isolation, and the /api/v1/research-lab API.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from core.research_lab import ResearchLab


def _lab() -> ResearchLab:
    return ResearchLab()


# ===========================================================================
# Definition
# ===========================================================================


class TestDefinition:
    def test_valid_definition(self) -> None:
        lab = _lab()
        experiment = lab.define(
            "pipeline_config",
            "moa on/off",
            tasks=["task one"],
            variants={"with_moa": {"enable_moa": True}, "without_moa": {"enable_moa": False}},
        )
        assert experiment.status == "pending"
        assert experiment.metric == "avg_latency_ms"

    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported kind"):
            _lab().define("quantum", "x", ["t"], {"a": {}, "b": {}})

    def test_single_variant_rejected(self) -> None:
        with pytest.raises(ValueError, match="two variants"):
            _lab().define("prompt", "x", ["t"], {"only": {"template": "t"}})

    def test_no_tasks_rejected(self) -> None:
        with pytest.raises(ValueError, match="task"):
            _lab().define("prompt", "x", [], {"a": {"template": "t"}, "b": {"template": "u"}})


# ===========================================================================
# Execution
# ===========================================================================


@pytest.mark.asyncio
class TestExecution:
    async def test_pipeline_config_experiment_real_measurements(self) -> None:
        lab = _lab()
        experiment = lab.define(
            "pipeline_config",
            "reflection on/off",
            tasks=["Research topic A", "Research topic B"],
            variants={
                "with_reflection": {"enable_reflection": True},
                "without_reflection": {"enable_reflection": False},
            },
        )
        result = await lab.run(experiment.experiment_id)
        assert result.status == "completed"
        for name in ("with_reflection", "without_reflection"):
            variant = result.results[name]
            assert variant["tasks_run"] == 2
            assert variant["avg_latency_ms"] > 0
            assert len(variant["request_ids"]) == 2  # real executions
        # reflection scores only where reflection ran
        assert result.results["with_reflection"]["avg_reflection_score"] is not None
        assert result.results["without_reflection"]["avg_reflection_score"] is None
        assert result.winner in ("with_reflection", "without_reflection")

    async def test_unknown_pipeline_field_fails_experiment(self) -> None:
        lab = _lab()
        experiment = lab.define(
            "pipeline_config", "bad field", ["t"],
            {"a": {"enable_warp": True}, "b": {}},
        )
        result = await lab.run(experiment.experiment_id)
        assert result.status == "failed"
        assert "enable_warp" in result.results["__error__"]["error"]

    async def test_prompt_experiment(self) -> None:
        lab = _lab()
        experiment = lab.define(
            "prompt",
            "terse vs verbose",
            tasks=["summarize the runtime"],
            variants={
                "terse": {"template": "Do: {{task}}"},
                "verbose": {"template": "Please carefully and thoroughly {{task}} with detail."},
            },
        )
        result = await lab.run(experiment.experiment_id)
        assert result.status == "completed"
        for variant in ("terse", "verbose"):
            assert result.results[variant]["success_rate"] == 1.0
            assert result.results[variant]["avg_answer_length"] > 0

    async def test_prompt_variant_requires_template(self) -> None:
        lab = _lab()
        experiment = lab.define(
            "prompt", "missing", ["t"],
            {"a": {"template": "x {{task}}"}, "b": {}},
        )
        result = await lab.run(experiment.experiment_id)
        assert result.status == "failed"

    async def test_memory_policy_experiment(self) -> None:
        lab = _lab()
        tasks = [f"memory item {i}" for i in range(30)]
        experiment = lab.define(
            "memory_policy",
            "aggressive vs conservative",
            tasks=tasks,
            variants={
                "aggressive": {
                    "archive_age_seconds": 0.0,
                    "archive_max_importance": 0.9,
                    "archive_max_access_count": 10,
                },
                "conservative": {"archive_age_seconds": 99999.0},
            },
            metric="total_after",
        )
        result = await lab.run(experiment.experiment_id)
        assert result.status == "completed"
        aggressive = result.results["aggressive"]
        conservative = result.results["conservative"]
        assert aggressive["seeded"] == 30
        # aggressive policy archived items; conservative did not
        assert aggressive["archived"] > 0
        assert conservative["archived"] == 0
        assert result.winner is not None

    async def test_run_unknown_experiment_raises(self) -> None:
        with pytest.raises(KeyError):
            await _lab().run("ghost")

    async def test_history(self) -> None:
        lab = _lab()
        first = lab.define("prompt", "one", ["t"],
                           {"a": {"template": "a {{task}}"}, "b": {"template": "b {{task}}"}})
        second = lab.define("prompt", "two", ["t"],
                            {"a": {"template": "a {{task}}"}, "b": {"template": "b {{task}}"}})
        listing = lab.list_experiments()
        assert [e.experiment_id for e in listing] == [
            second.experiment_id, first.experiment_id,
        ]


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


class TestResearchLabAPI:
    def test_full_experiment_flow(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/research-lab/experiments",
            json={
                "kind": "pipeline_config",
                "name": "moa toggle",
                "tasks": ["compare things"],
                "variants": {
                    "on": {"enable_moa": True},
                    "off": {"enable_moa": False},
                },
            },
        ).json()
        run = client.post(
            f"/api/v1/research-lab/experiments/{created['experiment_id']}/run"
        ).json()
        assert run["status"] == "completed"
        assert run["winner"] in ("on", "off")

        detail = client.get(
            f"/api/v1/research-lab/experiments/{created['experiment_id']}"
        )
        assert detail.status_code == 200
        listing = client.get("/api/v1/research-lab/experiments").json()
        assert listing["count"] == 1

    def test_invalid_definition_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/research-lab/experiments",
            json={
                "kind": "quantum",
                "name": "x",
                "tasks": ["t"],
                "variants": {"a": {}, "b": {}},
            },
        )
        assert resp.status_code == 422

    def test_unknown_experiment_404(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/research-lab/experiments/ghost/run").status_code
            == 404
        )
        assert (
            client.get("/api/v1/research-lab/experiments/ghost").status_code
            == 404
        )
