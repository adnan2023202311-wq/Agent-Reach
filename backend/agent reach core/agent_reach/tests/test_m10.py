"""
Tests for Milestone 10 features (M10.1–M10.10).

Covers:
- NodeRegistry (M10.1)
- AgentSwarm + SwarmOrchestrator (M10.2)
- GlobalAgentRegistry (M10.3)
- Plugin SDK (M10.4)
- API routers (M10.1–M10.10)
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── M10.1: NodeRegistry ────────────────────────────────────────────────

class TestNodeRegistry:
    def test_local_node_registered_on_init(self):
        from distributed.node_registry import NodeRegistry, NodeStatus
        registry = NodeRegistry()
        nodes = registry.list_nodes()
        assert len(nodes) == 1
        assert nodes[0].node_id == registry.local_node_id
        assert nodes[0].status == NodeStatus.ONLINE
        assert nodes[0].is_available()

    def test_register_and_deregister_remote_node(self):
        from distributed.node_registry import NodeRegistry, NodeInfo
        registry = NodeRegistry()
        remote = NodeInfo(endpoint="http://10.0.0.5:8000", capabilities=["research"])
        node_id = registry.register(remote)
        assert len(registry.list_nodes()) == 2
        assert registry.get(node_id) is not None

        # Can't deregister local
        assert registry.deregister(registry.local_node_id) is False
        # Can deregister remote
        assert registry.deregister(node_id) is True
        assert len(registry.list_nodes()) == 1

    def test_select_node_least_loaded(self):
        from distributed.node_registry import NodeRegistry, NodeInfo, NodeStatus
        registry = NodeRegistry()
        n1 = NodeInfo(endpoint="http://n1", capabilities=["research"], current_load=3)
        n2 = NodeInfo(endpoint="http://n2", capabilities=["research"], current_load=1)
        registry.register(n1)
        registry.register(n2)

        selected = registry.select_node(capability="research")
        # n2 has lower load, but local node (load 0) might win
        assert selected is not None
        assert selected.current_load <= 1

    def test_select_node_filters_by_capability(self):
        from distributed.node_registry import NodeRegistry, NodeInfo
        registry = NodeRegistry()
        remote = NodeInfo(endpoint="http://n1", capabilities=["coding"])
        registry.register(remote)

        # local has "research" in capabilities
        assert registry.select_node(capability="research") is not None
        # remote has "coding"
        selected = registry.select_node(capability="coding")
        assert selected is not None

    def test_cluster_stats(self):
        from distributed.node_registry import NodeRegistry
        registry = NodeRegistry()
        stats = registry.cluster_stats()
        assert stats["total_nodes"] == 1
        assert stats["online"] == 1
        assert stats["utilization"] == 0.0

    def test_heartbeat_updates_timestamp(self):
        from distributed.node_registry import NodeRegistry, NodeInfo
        registry = NodeRegistry()
        remote = NodeInfo(endpoint="http://n1")
        node_id = registry.register(remote)
        old_hb = registry.get(node_id).last_heartbeat
        import time; time.sleep(0.01)
        assert registry.heartbeat(node_id, load=2) is True
        updated = registry.get(node_id)
        assert updated.last_heartbeat > old_hb
        assert updated.current_load == 2


# ── M10.2: AgentSwarm ──────────────────────────────────────────────────

class TestAgentSwarm:
    def test_swarm_result_to_dict(self):
        from distributed.swarm import SwarmResult
        from domain.models import TaskStatus
        result = SwarmResult(swarm_id="test", objective="test objective")
        d = result.to_dict()
        assert d["swarm_id"] == "test"
        assert d["objective"] == "test objective"
        assert d["member_count"] == 0

    def test_default_scorer(self):
        from distributed.swarm import default_scorer
        score = default_scorer("machine learning model", "the machine learning model works great")
        assert score > 0

    def test_swarm_orchestrator_list_swarms_empty(self):
        from distributed.swarm import SwarmOrchestrator

        class FakeDispatcher:
            async def dispatch(self, subtask):
                from domain.models import AgentResult, TaskStatus
                return AgentResult(
                    subtask_id=subtask.id, agent_type=subtask.agent_type,
                    status=TaskStatus.SUCCEEDED, attempts=1, output="test", duration_ms=1.0,
                )

        orch = SwarmOrchestrator(FakeDispatcher())
        assert orch.list_swarms() == []

    def test_swarm_executes_and_scores(self):
        from distributed.swarm import SwarmOrchestrator, SwarmRole
        from domain.models import AgentType, TaskStatus, AgentResult

        class FakeDispatcher:
            async def dispatch(self, subtask):
                return AgentResult(
                    subtask_id=subtask.id, agent_type=subtask.agent_type,
                    status=TaskStatus.SUCCEEDED, attempts=1,
                    output=f"result for {subtask.description}", duration_ms=1.0,
                )

        orch = SwarmOrchestrator(FakeDispatcher())
        roles = [
            SwarmRole(role_name="analyst", agent_type=AgentType.RESEARCH),
            SwarmRole(role_name="coder", agent_type=AgentType.CODING),
        ]

        async def _run():
            return await orch.run("test objective", roles)

        result = asyncio.new_event_loop().run_until_complete(_run())
        assert result.status == TaskStatus.SUCCEEDED
        assert len(result.members) == 2
        assert result.winning_role in ("analyst", "coder")
        assert len(orch.list_swarms()) == 1


# ── M10.3: GlobalAgentRegistry ─────────────────────────────────────────

class TestGlobalAgentRegistry:
    def test_register_and_discover(self):
        from agents.global_registry import GlobalAgentRegistry, GlobalAgentEntry
        registry = GlobalAgentRegistry()
        entry = GlobalAgentEntry(
            agent_id="my-agent", name="My Agent", version="1.0.0",
            description="A test agent", category="research", tags=["test"],
        )
        registry.register(entry)
        results = registry.discover(query="test")
        assert len(results) == 1
        assert results[0].agent_id == "my-agent"

    def test_get_latest_version(self):
        from agents.global_registry import GlobalAgentRegistry, GlobalAgentEntry
        registry = GlobalAgentRegistry()
        registry.register(GlobalAgentEntry(agent_id="a", name="A", version="1.0.0"))
        registry.register(GlobalAgentEntry(agent_id="a", name="A", version="2.0.0"))
        latest = registry.get_latest("a")
        assert latest is not None
        assert latest.version == "2.0.0"

    def test_record_execution_updates_trust(self):
        from agents.global_registry import GlobalAgentRegistry, GlobalAgentEntry
        registry = GlobalAgentRegistry()
        registry.register(GlobalAgentEntry(agent_id="a", name="A", version="1.0.0"))
        registry.record_execution("a", "1.0.0", succeeded=True, latency_ms=100.0)
        entry = registry.get("a", "1.0.0")
        assert entry.trust.total_executions == 1
        assert entry.trust.successful_executions == 1
        assert entry.trust.success_rate == 1.0

    def test_verify_agent(self):
        from agents.global_registry import GlobalAgentRegistry, GlobalAgentEntry
        registry = GlobalAgentRegistry()
        registry.register(GlobalAgentEntry(agent_id="a", name="A", version="1.0.0"))
        assert registry.verify("a", "1.0.0") is True
        entry = registry.get("a", "1.0.0")
        assert entry.trust.verified is True

    def test_rate_agent(self):
        from agents.global_registry import GlobalAgentRegistry, GlobalAgentEntry
        registry = GlobalAgentRegistry()
        registry.register(GlobalAgentEntry(agent_id="a", name="A", version="1.0.0"))
        registry.rate("a", "1.0.0", stars=4.5)
        entry = registry.get("a", "1.0.0")
        assert entry.trust.community_rating == 4.5
        assert entry.trust.rating_count == 1


# ── M10.4: Plugin SDK ──────────────────────────────────────────────────

class TestPluginSDK:
    def test_manifest_to_dict(self):
        from sdk.plugin_sdk import PluginManifest
        manifest = PluginManifest(
            plugin_id="test", name="Test", version="1.0.0",
            plugin_type="tool", description="A test plugin",
        )
        d = manifest.to_dict()
        assert d["plugin_id"] == "test"
        assert d["plugin_type"] == "tool"

    def test_sdk_registry_register_and_list(self):
        from sdk.plugin_sdk import PluginSDKRegistry, PluginManifest, PluginTool

        class MyTool(PluginTool):
            @property
            def manifest(self):
                return PluginManifest(plugin_id="my-tool", name="My Tool", version="1.0.0", plugin_type="tool")
            @property
            def tool_name(self):
                return "my_tool"
            async def execute(self, **kwargs):
                return {"result": "ok"}

        registry = PluginSDKRegistry()
        tool = MyTool()
        registry.register(tool, tool.manifest)
        assert registry.get("my-tool") is not None
        tools = registry.list_by_type("tool")
        assert len(tools) == 1
        assert tools[0][0] == "my-tool"

    def test_plugin_types_exist(self):
        from sdk.plugin_sdk import PluginType
        assert PluginType.PROVIDER == "provider"
        assert PluginType.TOOL == "tool"
        assert PluginType.MEMORY_ADAPTER == "memory_adapter"
        assert PluginType.ROUTER == "router"
        assert PluginType.SKILL == "skill"
        assert PluginType.BENCHMARK == "benchmark"
        assert PluginType.VISUAL_NODE == "visual_node"


# ── M10 API routers ────────────────────────────────────────────────────

class TestM10APIRouters:
    def test_distributed_router_imports(self):
        from api.routers import distributed
        assert distributed.router is not None

    def test_global_agents_router_imports(self):
        from api.routers import global_agents
        assert global_agents.router is not None

    def test_sdk_router_imports(self):
        from api.routers import sdk
        assert sdk.router is not None

    def test_dev_platform_router_imports(self):
        from api.routers import dev_platform
        assert dev_platform.router is not None

    def test_workflows_v2_router_imports(self):
        from api.routers import workflows_v2
        assert workflows_v2.router is not None

    def test_enterprise_router_imports(self):
        from api.routers import enterprise
        assert enterprise.router is not None

    def test_apps_router_imports(self):
        from api.routers import apps
        assert apps.router is not None

    def test_marketplace_v2_router_imports(self):
        from api.routers import marketplace_v2
        assert marketplace_v2.router is not None

    def test_desktop_router_imports(self):
        from api.routers import desktop
        assert desktop.router is not None

    def test_app_has_m10_routes(self):
        from api.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        m10_paths = [
            "/api/v1/distributed/nodes",
            "/api/v1/distributed/swarm",
            "/api/v1/agents/global",
            "/api/v1/sdk/plugins",
            "/api/v1/dev-platform/api-keys",
            "/api/v1/workflows/v2",
            "/api/v1/enterprise/orgs",
            "/api/v1/apps",
            "/api/v1/marketplace/v2/items",
            "/api/v1/desktop/manifest",
        ]
        for path in m10_paths:
            assert path in routes, f"M10 route {path} not found in app routes"


# ── M10.7: Enterprise RBAC ─────────────────────────────────────────────

class TestEnterpriseRBAC:
    def test_role_permissions(self):
        from api.routers.enterprise import ROLE_PERMISSIONS
        assert "*" in ROLE_PERMISSIONS["owner"]
        assert "org.read" in ROLE_PERMISSIONS["member"]
        assert "org.read" in ROLE_PERMISSIONS["viewer"]
        assert "user.write" not in ROLE_PERMISSIONS["viewer"]


# ── M10.9: Marketplace V2 item types ───────────────────────────────────

class TestMarketplaceV2Types:
    def test_item_types_exist(self):
        from api.routers.marketplace_v2 import MarketplaceItemType
        assert MarketplaceItemType.AGENT == "agent"
        assert MarketplaceItemType.PLUGIN == "plugin"
        assert MarketplaceItemType.SKILL == "skill"
        assert MarketplaceItemType.TEMPLATE == "template"
        assert MarketplaceItemType.MEMORY_PACK == "memory_pack"
        assert MarketplaceItemType.PROMPT_PACK == "prompt_pack"
        assert MarketplaceItemType.WORKFLOW == "workflow"
        assert MarketplaceItemType.KNOWLEDGE_PACK == "knowledge_pack"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
