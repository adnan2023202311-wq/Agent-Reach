"""Tests for M9.6 — Live Tool Runtime and production tools.

Covers:
- FilesystemSandbox: real reads/writes/lists + escape rejection
- http_request / rss_fetch / browser_fetch against a real local HTTP
  server (no external network needed)
- telegram_send hard-fails without a token (no silent no-op)
- ToolRuntime: execution history, failures, retries, metrics
- /api/v1/tools endpoints: live registry data, execution, history,
  metrics, enable/disable
"""

from __future__ import annotations

import http.server
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_tool_runtime
from config.settings import get_settings
from core.tool_runtime import ToolRuntime
from domain.exceptions import ConfigurationError
from infrastructure.production_tools import (
    FilesystemSandbox,
    browser_fetch,
    http_request,
    register_production_tools,
    rss_fetch,
    telegram_send,
)
from infrastructure.tool_registry import ToolRegistry


# ===========================================================================
# Local HTTP fixture server — real sockets, no external network
# ===========================================================================

_RSS_BODY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Test Feed</title>
<item><title>First</title><link>http://example.com/1</link>
<description>Item one</description><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
<item><title>Second</title><link>http://example.com/2</link>
<description>Item two</description><pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate></item>
</channel></rss>"""

_ATOM_BODY = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry><title>Entry A</title><link href="http://example.com/a"/>
<summary>Summary A</summary><updated>2024-01-01T00:00:00Z</updated></entry>
</feed>"""

_HTML_BODY = """<html><head><title>Hello &amp; Welcome</title>
<style>body { color: red; }</style></head>
<body><script>var x = 1;</script>
<h1>Main Heading</h1><p>Readable text content.</p>
<a href="http://example.com/link1">One</a>
<a href="/relative">Two</a></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # silence test output
        pass

    def _send(self, body: str, content_type: str = "text/html") -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 — stdlib API
        if self.path == "/rss":
            self._send(_RSS_BODY, "application/rss+xml")
        elif self.path == "/atom":
            self._send(_ATOM_BODY, "application/atom+xml")
        elif self.path == "/page":
            self._send(_HTML_BODY)
        elif self.path == "/json":
            self._send('{"hello": "world"}', "application/json")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        self._send(f'{{"echo": {body or "null"}}}', "application/json")


@pytest.fixture(scope="module")
def local_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


# ===========================================================================
# FilesystemSandbox
# ===========================================================================


@pytest.mark.asyncio
class TestFilesystemSandbox:
    async def test_write_then_read(self, tmp_path) -> None:
        sandbox = FilesystemSandbox(tmp_path)
        await sandbox.write("notes/hello.txt", "hello world")
        result = await sandbox.read("notes/hello.txt")
        assert result["content"] == "hello world"

    async def test_append(self, tmp_path) -> None:
        sandbox = FilesystemSandbox(tmp_path)
        await sandbox.write("log.txt", "a")
        await sandbox.write("log.txt", "b", append=True)
        result = await sandbox.read("log.txt")
        assert result["content"] == "ab"

    async def test_list_dir(self, tmp_path) -> None:
        sandbox = FilesystemSandbox(tmp_path)
        await sandbox.write("one.txt", "1")
        await sandbox.write("sub/two.txt", "2")
        result = await sandbox.list_dir(".")
        names = {e["name"] for e in result["entries"]}
        assert names == {"one.txt", "sub"}

    async def test_escape_rejected(self, tmp_path) -> None:
        sandbox = FilesystemSandbox(tmp_path / "inner")
        with pytest.raises(PermissionError):
            await sandbox.read("../outside.txt")

    async def test_read_missing_raises(self, tmp_path) -> None:
        sandbox = FilesystemSandbox(tmp_path)
        with pytest.raises(FileNotFoundError):
            await sandbox.read("ghost.txt")


# ===========================================================================
# HTTP / RSS / Browser tools (real local server)
# ===========================================================================


@pytest.mark.asyncio
class TestHttpTools:
    async def test_http_get(self, local_server: str) -> None:
        result = await http_request(f"{local_server}/json")
        assert result["ok"] is True
        assert result["status_code"] == 200
        assert '"hello"' in result["body"]

    async def test_http_post_json(self, local_server: str) -> None:
        result = await http_request(
            f"{local_server}/json", method="POST", json_body={"a": 1}
        )
        assert result["ok"] is True
        assert '"echo"' in result["body"]

    async def test_http_invalid_method_rejected(self, local_server: str) -> None:
        with pytest.raises(ValueError):
            await http_request(f"{local_server}/json", method="BREW")

    async def test_rss_parse(self, local_server: str) -> None:
        result = await rss_fetch(f"{local_server}/rss")
        assert result["title"] == "Test Feed"
        assert result["count"] == 2
        assert result["items"][0]["title"] == "First"
        assert result["items"][0]["link"] == "http://example.com/1"

    async def test_atom_parse(self, local_server: str) -> None:
        result = await rss_fetch(f"{local_server}/atom")
        assert result["title"] == "Atom Feed"
        assert result["count"] == 1
        assert result["items"][0]["link"] == "http://example.com/a"

    async def test_rss_max_items(self, local_server: str) -> None:
        result = await rss_fetch(f"{local_server}/rss", max_items=1)
        assert result["count"] == 1

    async def test_browser_fetch_extracts_content(self, local_server: str) -> None:
        result = await browser_fetch(f"{local_server}/page")
        assert result["title"] == "Hello & Welcome"
        assert "Main Heading" in result["text"]
        assert "Readable text content." in result["text"]
        # script/style bodies must be stripped
        assert "var x" not in result["text"]
        assert "color: red" not in result["text"]
        assert "http://example.com/link1" in result["links"]


@pytest.mark.asyncio
class TestTelegramTool:
    async def test_unconfigured_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(ConfigurationError):
            await telegram_send("123", "hi")


# ===========================================================================
# ToolRuntime — history, retries, metrics
# ===========================================================================


@pytest.mark.asyncio
class TestToolRuntime:
    def _runtime(self, **kwargs) -> ToolRuntime:
        return ToolRuntime(ToolRegistry(), **kwargs)

    async def test_successful_execution_recorded(self) -> None:
        runtime = self._runtime()

        async def greet(who: str = "world") -> str:
            return f"hello {who}"

        runtime.registry.register("greet", greet, description="test")
        record = await runtime.execute("greet", parameters={"who": "reach"})
        assert record.success is True
        assert "hello reach" in record.output_preview
        assert len(runtime.get_history()) == 1

    async def test_unknown_tool_recorded_as_failure(self) -> None:
        runtime = self._runtime()
        record = await runtime.execute("nonexistent")
        assert record.success is False
        assert record.error
        assert record.attempts == 1  # not retried — not transient

    async def test_failure_retried_then_recorded(self) -> None:
        runtime = self._runtime(max_retries=2)
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        runtime.registry.register("flaky", flaky)
        record = await runtime.execute("flaky")
        assert record.success is True
        assert record.attempts == 3

    async def test_persistent_failure_exhausts_retries(self) -> None:
        runtime = self._runtime(max_retries=1)

        async def broken() -> None:
            raise RuntimeError("always broken")

        runtime.registry.register("broken", broken)
        record = await runtime.execute("broken")
        assert record.success is False
        assert record.attempts == 2
        assert "always broken" in record.error

    async def test_timeout_recorded(self) -> None:
        import asyncio

        runtime = self._runtime(max_retries=0)

        async def slow() -> None:
            await asyncio.sleep(5)

        runtime.registry.register("slow", slow)
        record = await runtime.execute("slow", timeout_seconds=0.05)
        assert record.success is False
        assert "timed out" in record.error

    async def test_disabled_tool_fails(self) -> None:
        runtime = self._runtime()

        async def noop() -> str:
            return "x"

        runtime.registry.register("noop", noop)
        runtime.registry.disable("noop")
        record = await runtime.execute("noop")
        assert record.success is False

    async def test_metrics_aggregate(self) -> None:
        runtime = self._runtime(max_retries=0)

        async def ok() -> str:
            return "fine"

        async def bad() -> None:
            raise RuntimeError("nope")

        runtime.registry.register("ok", ok)
        runtime.registry.register("bad", bad)
        await runtime.execute("ok")
        await runtime.execute("ok")
        await runtime.execute("bad")
        metrics = runtime.get_metrics()
        assert metrics["total_executions"] == 3
        assert metrics["successes"] == 2
        assert metrics["failures"] == 1
        per_tool = runtime.get_per_tool_metrics()
        assert per_tool["ok"]["success_rate"] == 1.0
        assert per_tool["bad"]["success_rate"] == 0.0

    async def test_history_filters(self) -> None:
        runtime = self._runtime(max_retries=0)

        async def ok() -> str:
            return "fine"

        runtime.registry.register("ok", ok)
        await runtime.execute("ok")
        await runtime.execute("missing_tool")
        assert len(runtime.get_history(failures_only=True)) == 1
        assert len(runtime.get_history(tool_name="ok")) == 1

    async def test_empty_metrics_honest_zeros(self) -> None:
        runtime = self._runtime()
        metrics = runtime.get_metrics()
        assert metrics["total_executions"] == 0
        assert metrics["success_rate"] == 0.0


# ===========================================================================
# Composition + API
# ===========================================================================


class TestBuildToolRuntime:
    def test_production_tools_registered(self) -> None:
        runtime = build_tool_runtime()
        names = {m.name for m in runtime.registry.list_tools()}
        assert {
            "http_request",
            "rss_fetch",
            "browser_fetch",
            "fs_read",
            "fs_write",
            "fs_list",
            "telegram_send",
        } <= names

    def test_telegram_disabled_without_token(self, monkeypatch) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        registry = ToolRegistry()
        register_production_tools(registry)
        meta = registry.get_metadata("telegram_send")
        assert meta.enabled is False


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


class TestToolsAPI:
    def test_list_tools_live_registry(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools")
        assert resp.status_code == 200
        tools = resp.json()
        ids = {t["id"] for t in tools}
        assert "http_request" in ids
        assert "fs_write" in ids
        http_tool = next(t for t in tools if t["id"] == "http_request")
        assert http_tool["version"] == "1.0.0"
        assert http_tool["enabled"] is True

    def test_get_single_tool(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools/rss_fetch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "rss_fetch"
        assert "metrics" in data
        assert "recent_executions" in data

    def test_get_unknown_tool_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/tools/warp_drive").status_code == 404

    def test_execute_fs_tool_end_to_end(self, client: TestClient) -> None:
        write = client.post(
            "/api/v1/tools/fs_write/execute",
            json={"parameters": {"path": "api_test.txt", "content": "from the api"}},
        )
        assert write.status_code == 200
        assert write.json()["success"] is True

        read = client.post(
            "/api/v1/tools/fs_read/execute",
            json={"parameters": {"path": "api_test.txt"}},
        )
        assert read.json()["success"] is True
        assert "from the api" in read.json()["output_preview"]

    def test_execution_appears_in_history_and_metrics(self, client: TestClient) -> None:
        client.post(
            "/api/v1/tools/fs_list/execute", json={"parameters": {"path": "."}}
        )
        history = client.get("/api/v1/tools/history?tool_id=fs_list").json()
        assert history["count"] >= 1
        metrics = client.get("/api/v1/tools/metrics").json()
        assert metrics["overall"]["total_executions"] >= 1
        assert "fs_list" in metrics["per_tool"]

    def test_failed_execution_returns_record(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/tools/fs_read/execute",
            json={"parameters": {"path": "no_such_file.txt"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"]

    def test_execute_unknown_tool_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tools/warp_drive/execute", json={})
        assert resp.status_code == 404

    def test_enable_disable_roundtrip(self, client: TestClient) -> None:
        off = client.patch("/api/v1/tools/rss_fetch", json={"enabled": False})
        assert off.status_code == 200
        assert off.json()["enabled"] is False
        # Disabled tool execution is recorded as failure.
        run = client.post("/api/v1/tools/rss_fetch/execute", json={"parameters": {"url": "http://localhost/x"}})
        assert run.json()["success"] is False
        on = client.patch("/api/v1/tools/rss_fetch", json={"enabled": True})
        assert on.json()["enabled"] is True

    def test_patch_without_enabled_422(self, client: TestClient) -> None:
        resp = client.patch("/api/v1/tools/rss_fetch", json={"name": "x"})
        assert resp.status_code == 422
