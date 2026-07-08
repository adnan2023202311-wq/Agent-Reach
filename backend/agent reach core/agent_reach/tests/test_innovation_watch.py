"""Tests for M9.16/M9.31 — Research Engine & Innovation Watch.

Proves: transparent keyword relevance scoring, scanning through the
REAL tool runtime against a local RSS server (recorded in tool
history), threshold-gated finding registration with URL dedupe,
knowledge-graph storage into the SHARED graph, per-source error
isolation, model evaluation (advisory + trace-linked), compatibility
reports against the real M9.26 contracts, and the API.
"""

from __future__ import annotations

import http.server
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline, build_tool_runtime
from config.settings import get_settings
from core.innovation_watch import InnovationWatch, score_relevance
from knowledge.graph import KnowledgeGraph, NodeType


_RELEVANT_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>AI Research Feed</title>
<item><title>New multi-agent memory system with vector retrieval</title>
<link>http://example.com/paper-1</link>
<description>A memory and retrieval architecture for agent collaboration and routing.</description></item>
<item><title>Cooking recipes weekly</title>
<link>http://example.com/recipes</link>
<description>Seven pasta dishes for the weekend.</description></item>
</channel></rss>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/feed":
            payload = _RELEVANT_RSS.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def rss_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


# ===========================================================================
# Scoring
# ===========================================================================


class TestScoring:
    def test_relevant_text_scores(self) -> None:
        topics, score = score_relevance(
            "A multi-agent memory system using vector retrieval and routing"
        )
        assert score >= 4
        assert "memory_systems" in topics
        assert "multi_agent" in topics

    def test_irrelevant_text_scores_zero(self) -> None:
        topics, score = score_relevance("Seven pasta dishes for the weekend")
        assert score == 0
        assert topics == {}


# ===========================================================================
# Watch
# ===========================================================================


@pytest.mark.asyncio
class TestWatch:
    async def test_scan_registers_only_relevant_items(self, rss_server: str) -> None:
        tool_runtime = build_tool_runtime()
        graph = KnowledgeGraph()
        watch = InnovationWatch(tool_runtime, knowledge_graph=graph)
        watch.add_source(f"{rss_server}/feed", kind="rss", label="test feed")

        result = await watch.scan()
        assert result["new_count"] == 1  # recipes filtered out
        finding = result["new_findings"][0]
        assert "multi-agent" in finding["title"]
        assert finding["relevance_score"] >= 2
        # the fetch went through the REAL tool runtime
        assert tool_runtime.get_metrics("rss_fetch")["total_executions"] >= 1
        # the finding landed in the SHARED knowledge graph
        node = graph.get_node(finding["knowledge_node_id"])
        assert node is not None
        assert node.node_type == NodeType.DOCUMENT
        assert 0.3 <= node.confidence <= 0.9

    async def test_rescan_deduplicates_by_url(self, rss_server: str) -> None:
        watch = InnovationWatch(build_tool_runtime())
        watch.add_source(f"{rss_server}/feed")
        first = await watch.scan()
        second = await watch.scan()
        assert first["new_count"] == 1
        assert second["new_count"] == 0

    async def test_source_error_isolated(self, rss_server: str) -> None:
        watch = InnovationWatch(build_tool_runtime())
        watch.add_source(f"{rss_server}/does-not-exist")
        watch.add_source(f"{rss_server}/feed")
        result = await watch.scan()
        assert result["new_count"] == 1
        assert len(result["errors"]) == 1
        broken = next(
            s for s in watch.list_sources() if "does-not-exist" in s.url
        )
        assert broken.last_error is not None

    async def test_evaluation_advisory_and_trace_linked(self, rss_server: str) -> None:
        pipeline = build_intelligent_pipeline()
        watch = InnovationWatch(build_tool_runtime(), pipeline=pipeline)
        watch.add_source(f"{rss_server}/feed")
        scan = await watch.scan()
        finding_id = scan["new_findings"][0]["finding_id"]

        finding = await watch.evaluate(finding_id)
        assert finding.evaluation["available"] is True
        assert "advisory" in finding.evaluation["note"].lower()
        assert pipeline.get_trace(finding.evaluation["request_id"]) is not None

    async def test_evaluation_without_pipeline_honest(self, rss_server: str) -> None:
        watch = InnovationWatch(build_tool_runtime())
        watch.add_source(f"{rss_server}/feed")
        scan = await watch.scan()
        finding = await watch.evaluate(scan["new_findings"][0]["finding_id"])
        assert finding.evaluation["available"] is False

    async def test_compatibility_report_uses_real_contracts(self, rss_server: str) -> None:
        watch = InnovationWatch(build_tool_runtime())
        watch.add_source(f"{rss_server}/feed")
        scan = await watch.scan()
        report = watch.compatibility_report(scan["new_findings"][0]["finding_id"])
        categories = {c["category"] for c in report["candidate_adapter_categories"]}
        assert "memory" in categories  # memory_systems topic → memory adapter
        memory_contract = next(
            c for c in report["candidate_adapter_categories"]
            if c["category"] == "memory"
        )
        method_names = {m["name"] for m in memory_contract["required_interface"]}
        assert {"store", "retrieve_relevant"} <= method_names
        assert "never deploys" in report["note"]

    async def test_unknown_finding_raises(self) -> None:
        watch = InnovationWatch(build_tool_runtime())
        with pytest.raises(KeyError):
            await watch.evaluate("ghost")
        with pytest.raises(KeyError):
            watch.compatibility_report("ghost")

    async def test_source_validation(self) -> None:
        watch = InnovationWatch(build_tool_runtime())
        with pytest.raises(ValueError):
            watch.add_source("", kind="rss")
        with pytest.raises(ValueError):
            watch.add_source("http://x", kind="telepathy")


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


class TestInnovationAPI:
    def test_source_lifecycle(self, client: TestClient, rss_server: str) -> None:
        created = client.post(
            "/api/v1/innovation/sources",
            json={"url": f"{rss_server}/feed", "label": "research"},
        ).json()
        listing = client.get("/api/v1/innovation/sources").json()
        assert listing["count"] == 1
        removed = client.delete(
            f"/api/v1/innovation/sources/{created['source_id']}"
        )
        assert removed.status_code == 200

    def test_scan_and_findings_flow(self, client: TestClient, rss_server: str) -> None:
        client.post(
            "/api/v1/innovation/sources", json={"url": f"{rss_server}/feed"}
        )
        scan = client.post("/api/v1/innovation/scan").json()
        assert scan["new_count"] == 1

        findings = client.get("/api/v1/innovation/findings").json()
        assert findings["count"] == 1
        finding_id = findings["findings"][0]["finding_id"]

        compat = client.get(
            f"/api/v1/innovation/findings/{finding_id}/compatibility"
        ).json()
        assert compat["candidate_adapter_categories"]

        evaluated = client.post(
            f"/api/v1/innovation/findings/{finding_id}/evaluate"
        ).json()
        assert evaluated["evaluation"]["available"] is True

        # The finding is visible on the shared Knowledge screen too.
        graph = client.get("/api/v1/knowledge/graph").json()
        assert any(
            n["id"] == findings["findings"][0]["knowledge_node_id"]
            for n in graph["nodes"]
        )

    def test_unknown_finding_404(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/innovation/findings/ghost").status_code == 404
        )
        assert (
            client.post("/api/v1/innovation/findings/ghost/evaluate").status_code
            == 404
        )

    def test_invalid_source_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/innovation/sources", json={"url": "http://x", "kind": "psychic"}
        )
        assert resp.status_code == 422

    def test_stats(self, client: TestClient) -> None:
        stats = client.get("/api/v1/innovation/stats").json()
        assert stats["sources"] == 0
        assert stats["total_findings"] == 0
