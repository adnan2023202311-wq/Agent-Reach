"""Tests for M9.15 — AI Code Review System.

Proves: deterministic AST findings (security/maintainability/
readability/correctness), architecture layering checks from the
project's own rules, verdict derivation (blocked/changes_requested/
approved) from static findings only, model narrative advisory tier
(trace-linked, never changes the verdict), history/stats, and the
/api/v1/code-review endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings
from core.code_review import CodeReviewEngine


def _findings_by_check(result, check: str):
    return [f for f in result.findings if f.check == check]


# ===========================================================================
# Static analysis
# ===========================================================================


class TestStaticAnalysis:
    def _engine(self) -> CodeReviewEngine:
        return CodeReviewEngine()

    def test_clean_code_approved(self) -> None:
        source = (
            'def add(a: int, b: int) -> int:\n'
            '    """Add two integers."""\n'
            '    return a + b\n'
        )
        result = self._engine().review(source)
        assert result.verdict == "approved"
        assert result.findings == []

    def test_eval_blocked(self) -> None:
        result = self._engine().review("def run(code):\n    return eval(code)\n")
        security = _findings_by_check(result, "security")
        assert any("eval" in f.message for f in security)
        assert result.verdict == "blocked"

    def test_shell_true_blocked(self) -> None:
        source = (
            "import subprocess\n"
            "def go(cmd):\n"
            "    subprocess.run(cmd, shell=True)\n"
        )
        result = self._engine().review(source)
        assert any("shell=True" in f.message for f in result.findings)
        assert result.verdict == "blocked"

    def test_hardcoded_secret_blocked(self) -> None:
        result = self._engine().review('API_KEY = "sk-abcdef1234567890"\n')
        assert any("secret" in f.message.lower() for f in result.findings)
        assert result.verdict == "blocked"

    def test_bare_except_warns(self) -> None:
        source = (
            "def risky():\n"
            "    try:\n"
            "        pass\n"
            "    except:\n"
            "        pass\n"
        )
        result = self._engine().review(source)
        assert any("except" in f.message for f in result.findings)
        assert result.verdict == "changes_requested"

    def test_mutable_default_warns(self) -> None:
        result = self._engine().review("def f(items=[]):\n    return items\n")
        correctness = _findings_by_check(result, "correctness")
        assert len(correctness) == 1

    def test_too_many_parameters_warns(self) -> None:
        source = "def f(a, b, c, d, e, g, h, i):\n    pass\n"
        result = self._engine().review(source)
        assert any("parameters" in f.message for f in result.findings)

    def test_long_function_warns(self) -> None:
        body = "\n".join(f"    x{i} = {i}" for i in range(85))
        result = self._engine().review(f"def big():\n{body}\n")
        assert any("spans" in f.message for f in result.findings)

    def test_missing_docstring_is_info_only(self) -> None:
        result = self._engine().review("def public():\n    return 1\n")
        assert result.verdict == "approved"  # info never gates
        assert any(f.severity == "info" for f in result.findings)

    def test_private_function_no_docstring_finding(self) -> None:
        result = self._engine().review("def _internal():\n    return 1\n")
        assert _findings_by_check(result, "readability") == []

    def test_syntax_error_blocks(self) -> None:
        result = self._engine().review("def broken(:\n")
        assert result.parse_error is not None
        assert result.verdict == "blocked"

    def test_deep_nesting_warns(self) -> None:
        source = (
            "def nested():\n"
            "    if 1:\n"
            "        if 2:\n"
            "            if 3:\n"
            "                if 4:\n"
            "                    if 5:\n"
            "                        if 6:\n"
            "                            pass\n"
        )
        result = self._engine().review(source)
        assert any("nests" in f.message for f in result.findings)


class TestArchitectureRules:
    def test_core_importing_api_flagged(self) -> None:
        engine = CodeReviewEngine()
        result = engine.review(
            "from api.main import create_app\n",
            file_path="core/new_feature.py",
        )
        arch = _findings_by_check(result, "architecture")
        assert len(arch) == 1
        assert "core/ must not import" in arch[0].message

    def test_domain_importing_infrastructure_flagged(self) -> None:
        engine = CodeReviewEngine()
        result = engine.review(
            "import infrastructure.tool_manager\n",
            file_path="domain/new_model.py",
        )
        assert len(_findings_by_check(result, "architecture")) == 1

    def test_no_file_path_skips_layering(self) -> None:
        engine = CodeReviewEngine()
        result = engine.review("from api.main import create_app\n")
        assert _findings_by_check(result, "architecture") == []

    def test_legal_import_not_flagged(self) -> None:
        engine = CodeReviewEngine()
        result = engine.review(
            "from domain.models import AgentType\n",
            file_path="core/feature.py",
        )
        assert _findings_by_check(result, "architecture") == []


# ===========================================================================
# Model tier
# ===========================================================================


@pytest.mark.asyncio
class TestModelReview:
    async def test_narrative_is_advisory_and_trace_linked(self) -> None:
        pipeline = build_intelligent_pipeline()
        engine = CodeReviewEngine(pipeline)
        result = await engine.review_with_model(
            "def run(code):\n    return eval(code)\n", file_path="tool.py"
        )
        # verdict still comes from static findings
        assert result.verdict == "blocked"
        assert result.model_review["available"] is True
        assert "advisory" in result.model_review["note"]
        # the narrative execution is a real persisted trace
        assert pipeline.get_trace(result.model_review["request_id"]) is not None

    async def test_no_pipeline_is_honest(self) -> None:
        engine = CodeReviewEngine()
        result = await engine.review_with_model("x = 1\n")
        assert result.model_review["available"] is False


class TestHistory:
    def test_reviews_stored_and_stats(self) -> None:
        engine = CodeReviewEngine()
        first = engine.review("x = eval('1')\n")
        second = engine.review('def ok() -> int:\n    """Ok."""\n    return 1\n')
        assert engine.get_review(first.review_id) is first
        listing = engine.list_reviews()
        assert [r.review_id for r in listing] == [second.review_id, first.review_id]
        stats = engine.get_stats()
        assert stats["total_reviews"] == 2
        assert stats["verdicts"]["blocked"] == 1
        assert stats["verdicts"]["approved"] == 1


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


class TestCodeReviewAPI:
    def test_static_review_endpoint(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/code-review",
            json={"source": "def f(items=[]):\n    return items\n"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "changes_requested"
        assert data["model_review"] is None

    def test_model_review_endpoint(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/code-review",
            json={
                "source": "x = 1\n",
                "include_model_review": True,
            },
        )
        data = resp.json()
        assert data["model_review"]["available"] is True
        # narrative execution observable in the observatory
        trace = client.get(
            f"/api/v1/observatory/trace/{data['model_review']['request_id']}"
        )
        assert trace.status_code == 200

    def test_history_and_stats_endpoints(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/code-review", json={"source": "x = 1\n"}
        ).json()
        detail = client.get(f"/api/v1/code-review/reviews/{created['review_id']}")
        assert detail.status_code == 200
        stats = client.get("/api/v1/code-review/stats").json()
        assert stats["total_reviews"] >= 1

    def test_unknown_review_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/code-review/reviews/ghost").status_code == 404

    def test_empty_source_422(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/code-review", json={"source": ""}).status_code
            == 422
        )
