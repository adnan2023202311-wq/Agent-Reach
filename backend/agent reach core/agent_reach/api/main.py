"""
API layer: FastAPI application factory.

Layer: Interface/Presentation (outermost besides composition.py).

This is intentionally the only module that imports FastAPI, builds the
app, and triggers the composition root — every other module in the
codebase can be imported and unit-tested without a running web server.
The MainController is built inside `lifespan`, at actual server
startup, not at import time — a router that builds a `MainController()``
singleton as an import-time side effect makes it impossible to swap in
a test double without monkeypatching.

This backend no longer serves the frontend itself. Milestone 5's
frontend/index.html was a single static file, so mounting it directly
on this FastAPI app cost nothing. Milestone 6 replaced it with the
production Lovable frontend — a full TanStack Start app with its own
Vite dev server and Nitro-based SSR build — which runs as its own
process and talks to this API over HTTP (see frontend/README.md and
frontend/.env.example for how it's configured to find this backend).
That's why CORS is now load-bearing: Settings.allowed_origins must
include wherever `bun run dev` actually serves the frontend from.

Milestone 6 additions:
- ConversationEngine, SessionManager, WorkflowEngine, and
  WorkflowRegistry are built in the lifespan and stored on app.state
  so the new routers (conversations, workflows) can access them.
- New routers: conversations, workflows.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.exception_handlers import register_exception_handlers
from api.routers import agents, chat, conversations, dashboard, health, providers, tools, workflows
# Milestone 8 routers — imported via a helper that LOGS failures.
# M9.1: the previous bare try/except silently dropped routers whose
# imports failed (e.g. a missing dependency), leaving whole screens
# dead with no diagnostic. Failures are now visible in the logs.
import importlib
import logging

_logger = logging.getLogger(__name__)


def _try_import_router(module_name: str):
    try:
        return importlib.import_module(f"api.routers.{module_name}")
    except Exception:
        _logger.exception(
            "Router 'api.routers.%s' failed to import and will NOT be mounted",
            module_name,
        )
        return None


memory_router = _try_import_router("memory")
knowledge_router = _try_import_router("knowledge")
prompts_router = _try_import_router("prompts_studio")
observatory_router = _try_import_router("observatory")
skills_router = _try_import_router("skills")
# M8 extended
marketplace_router = _try_import_router("marketplace")
playground_router = _try_import_router("playground")
connectors_router = _try_import_router("connectors")
collaboration_router = _try_import_router("collaboration")
agent_studio_router = _try_import_router("agent_studio")
# M9.24
events_router = _try_import_router("events")
optimization_router = _try_import_router("optimization")
benchmark_lab_router = _try_import_router("benchmark_lab")
improvement_router = _try_import_router("improvement")
collaboration_engine_router = _try_import_router("collaboration_engine")
adapters_router = _try_import_router("adapters")
platform_router = _try_import_router("platform")
qa_router = _try_import_router("qa")
code_review_router = _try_import_router("code_review")
organization_router = _try_import_router("organization")
innovation_router = _try_import_router("innovation")
auto_integration_router = _try_import_router("auto_integration")
research_lab_router = _try_import_router("research_lab")
release_router = _try_import_router("release")
# M10 routers
distributed_router = _try_import_router("distributed")
global_agents_router = _try_import_router("global_agents")
sdk_router = _try_import_router("sdk")
dev_platform_router = _try_import_router("dev_platform")
workflows_v2_router = _try_import_router("workflows_v2")
enterprise_router = _try_import_router("enterprise")
apps_router = _try_import_router("apps")
marketplace_v2_router = _try_import_router("marketplace_v2")
desktop_router = _try_import_router("desktop")
# M10.11–M10.20 routers
mobile_router = _try_import_router("mobile")
sync_router = _try_import_router("sync")
monitoring_router = _try_import_router("monitoring")
security_router = _try_import_router("security")
billing_router = _try_import_router("billing")
infrastructure_router = _try_import_router("infrastructure")
connectors_v2_router = _try_import_router("connectors_v2")
collaboration_v2_router = _try_import_router("collaboration_v2")
app_store_router = _try_import_router("app_store")
agi_router = _try_import_router("agi")
# M10.21–M10.30 routers
intelligence_router = _try_import_router("intelligence")
planet_scale_router = _try_import_router("planet_scale")
federation_router = _try_import_router("federation")
evolution_router = _try_import_router("evolution")
memory_v2_router = _try_import_router("memory_v2")
router_v2_router = _try_import_router("router_v2")
engineering_memory_router = _try_import_router("engineering_memory")
error_intelligence_router = _try_import_router("error_intelligence")
repository_router = _try_import_router("repository")
workspace_v2_router = _try_import_router("workspace_v2")
# M10.31–M10.38 routers
reliability_router = _try_import_router("reliability")
engineering_router = _try_import_router("engineering")
engineering_extensions_router = _try_import_router("engineering_extensions")
runtime_extensions_router = _try_import_router("runtime_extensions")
project_dna_router = _try_import_router("project_dna")
analytics_router = _try_import_router("analytics")
cache_router = _try_import_router("cache")
workflow_intelligence_router = _try_import_router("workflow_intelligence")
from composition import (
    build_default_controller,
    build_conversation_engine,
    build_event_hub,
    build_intelligent_pipeline,
    build_tool_runtime,
    build_workflow_engine,
    build_workflow_registry,
)
from config.logging_config import configure_logging
from config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Build the core controller (backward compatible)
        app.state.controller = build_default_controller(settings)
        # M9.24: runtime event hub — the pipeline publishes the
        # canonical event chain through the existing EventBus.
        app.state.event_hub = build_event_hub()
        # Build the M7.5 intelligent pipeline (recommended entry point)
        app.state.pipeline = build_intelligent_pipeline(
            settings, event_hub=app.state.event_hub
        )
        # Build M6 components.
        app.state.conversation_engine = build_conversation_engine(settings)
        app.state.session_manager = app.state.conversation_engine._session_manager
        app.state.workflow_engine = build_workflow_engine(settings)
        app.state.workflow_registry = build_workflow_registry()
        # M9.6: live tool runtime — real tools, execution history, metrics.
        app.state.tool_runtime = build_tool_runtime(settings)
        # M9.10: workflow run manager — pause/resume/retry/cancel on the
        # SAME engine instance the /workflows router uses.
        from workflows.run_manager import WorkflowRunManager

        app.state.workflow_run_manager = WorkflowRunManager(
            app.state.workflow_engine
        )
        # M9.9: Agent Studio — runs custom agents through the SHARED
        # intelligent pipeline (real traces, real observability).
        from agents.studio import AgentStudio

        app.state.agent_studio = AgentStudio(app.state.pipeline)
        # M9.22: real plugin marketplace, seeded from the live tool
        # registry (no hardcoded catalog).
        from api.routers.marketplace import seed_marketplace_from_tools
        from marketplace import PluginMarketplace

        app.state.plugin_marketplace = PluginMarketplace()
        seed_marketplace_from_tools(
            app.state.plugin_marketplace, app.state.tool_runtime
        )
        # M9.14: self-optimization engine over the shared pipeline.
        from core.self_optimization import SelfOptimizationEngine

        app.state.optimization_engine = SelfOptimizationEngine(app.state.pipeline)
        # M9.20: prompt evolution over the M7 PromptIntelligence.
        from prompts.evolution import PromptEvolutionEngine

        app.state.prompt_evolution = PromptEvolutionEngine()
        # M9.19: benchmark lab feeding the pipeline's SHARED router.
        from benchmarks.provider_lab import ProviderBenchmarkLab

        app.state.benchmark_lab = ProviderBenchmarkLab(
            settings, app.state.pipeline._get_router()
        )
        # M9.23: enterprise engine — real orgs/teams/workspaces/RBAC/audit.
        from enterprise import EnterpriseEngine

        app.state.enterprise = EnterpriseEngine()
        # M9.27: continuous self-improvement loop, advanced by real
        # pipeline events (M9.24) — no background threads.
        from core.self_improvement import SelfImprovementLoop

        app.state.improvement_loop = SelfImprovementLoop(
            app.state.pipeline,
            app.state.optimization_engine,
            app.state.prompt_evolution,
        )
        app.state.improvement_loop.attach(app.state.event_hub)
        # M9.21: adaptive memory evolution over the pipeline's SHARED
        # LongCat engine.
        from memory.adaptive import AdaptiveMemoryManager

        app.state.adaptive_memory = AdaptiveMemoryManager(
            app.state.pipeline._get_memory()
        )
        # M9.29: multi-agent collaboration over the SHARED controller's
        # planner + dispatcher (no parallel agent stack).
        from core.collaboration_engine import CollaborationEngine

        app.state.collaboration_engine = CollaborationEngine(
            app.state.controller._planner,
            app.state.controller._dispatcher,
        )
        # M9.26: Future AI Layer adapter registry over the shared
        # pipeline + tool runtime.
        from infrastructure.adapters import AdapterRegistry

        app.state.adapter_registry = AdapterRegistry(
            app.state.pipeline, app.state.tool_runtime
        )
        # M9.11: platform introspection over the live app + pipeline.
        from core.platform_introspection import PlatformIntrospection

        app.state.platform_introspection = PlatformIntrospection(
            app.state.pipeline, app.state.tool_runtime, app
        )
        # M9.13: QA framework over the shared runtime evidence.
        from core.qa_framework import QAFramework

        app.state.qa_framework = QAFramework(
            app.state.pipeline,
            app.state.tool_runtime,
            app.state.workflow_run_manager,
            app.state.platform_introspection,
        )
        # M9.15: code review — static verdict authority + optional
        # model narrative through the shared pipeline.
        from core.code_review import CodeReviewEngine

        app.state.code_review = CodeReviewEngine(app.state.pipeline)
        # M9.12: engineering organization on the shared pipeline.
        from agents.organization import EngineeringOrganization

        app.state.engineering_organization = EngineeringOrganization(
            app.state.pipeline
        )
        # M9.16/M9.31: innovation watch over the real tool runtime,
        # shared pipeline (evaluation), and shared knowledge graph.
        from core.innovation_watch import InnovationWatch

        app.state.innovation_watch = InnovationWatch(
            app.state.tool_runtime,
            app.state.pipeline,
            app.state.pipeline._get_knowledge_graph(),
        )
        # M9.17: auto-integration over the M9.26 adapter registry.
        from infrastructure.auto_integration import AutoIntegrationEngine

        app.state.auto_integration = AutoIntegrationEngine(
            app.state.adapter_registry, app.state.pipeline
        )
        # M9.28: research lab for controlled experimentation.
        from core.research_lab import ResearchLab

        app.state.research_lab = ResearchLab()
        # M9.25/M9.30: release pipeline gated on every validation.
        from core.release_pipeline import ReleasePipeline

        app.state.release_pipeline = ReleasePipeline(
            app.state.pipeline,
            app.state.platform_introspection,
            app.state.qa_framework,
            app.state.code_review,
        )
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(workflows.router)
    app.include_router(agents.router)
    app.include_router(tools.router)
    app.include_router(providers.router)
    app.include_router(dashboard.router)

    # Milestone 8 routers
    if memory_router:
        app.include_router(memory_router.router)
    if knowledge_router:
        app.include_router(knowledge_router.router)
    if prompts_router:
        app.include_router(prompts_router.router)
    if observatory_router:
        app.include_router(observatory_router.router)
    if skills_router:
        app.include_router(skills_router.router)
    # M8 extended
    if marketplace_router:
        app.include_router(marketplace_router.router)
    if playground_router:
        app.include_router(playground_router.router)
    if connectors_router:
        app.include_router(connectors_router.router)
    if collaboration_router:
        app.include_router(collaboration_router.router)
    if agent_studio_router:
        app.include_router(agent_studio_router.router)
    # M9.24
    if events_router:
        app.include_router(events_router.router)
    # M9.14
    if optimization_router:
        app.include_router(optimization_router.router)
    # M9.19
    if benchmark_lab_router:
        app.include_router(benchmark_lab_router.router)
    # M9.27
    if improvement_router:
        app.include_router(improvement_router.router)
    # M9.29
    if collaboration_engine_router:
        app.include_router(collaboration_engine_router.router)
    # M9.26
    if adapters_router:
        app.include_router(adapters_router.router)
    # M9.11
    if platform_router:
        app.include_router(platform_router.router)
    # M9.13
    if qa_router:
        app.include_router(qa_router.router)
    # M9.15
    if code_review_router:
        app.include_router(code_review_router.router)
    # M9.12
    if organization_router:
        app.include_router(organization_router.router)
    # M9.16 / M9.31
    if innovation_router:
        app.include_router(innovation_router.router)
    # M9.17
    if auto_integration_router:
        app.include_router(auto_integration_router.router)
    # M9.28
    if research_lab_router:
        app.include_router(research_lab_router.router)
    # M9.25 / M9.30
    if release_router:
        app.include_router(release_router.router)

    # ── Milestone 10 routers ─────────────────────────────────────
    # M10.1 + M10.2: Distributed Agent Cloud + Swarm Intelligence
    if distributed_router:
        app.include_router(distributed_router.router)
    # M10.3: Global Agent Registry
    if global_agents_router:
        app.include_router(global_agents_router.router)
    # M10.4: Plugin SDK
    if sdk_router:
        app.include_router(sdk_router.router)
    # M10.5: Public Developer Platform
    if dev_platform_router:
        app.include_router(dev_platform_router.router)
    # M10.6: Visual Workflow Builder V2
    if workflows_v2_router:
        app.include_router(workflows_v2_router.router)
    # M10.7: Enterprise Deployment Platform
    if enterprise_router:
        app.include_router(enterprise_router.router)
    # M10.8: AI Application Builder
    if apps_router:
        app.include_router(apps_router.router)
    # M10.9: Marketplace V2
    if marketplace_v2_router:
        app.include_router(marketplace_v2_router.router)
    # M10.10: AI Operating System Desktop
    if desktop_router:
        app.include_router(desktop_router.router)

    # ── Milestone 10 Batch 2 routers (M10.11–M10.20) ────────────
    if mobile_router:
        app.include_router(mobile_router.router)
    if sync_router:
        app.include_router(sync_router.router)
    if monitoring_router:
        app.include_router(monitoring_router.router)
    if security_router:
        app.include_router(security_router.router)
    if billing_router:
        app.include_router(billing_router.router)
    if infrastructure_router:
        app.include_router(infrastructure_router.router)
    if connectors_v2_router:
        app.include_router(connectors_v2_router.router)
    if collaboration_v2_router:
        app.include_router(collaboration_v2_router.router)
    if app_store_router:
        app.include_router(app_store_router.router)
    if agi_router:
        app.include_router(agi_router.router)

    # ── Milestone 10 Batch 3 routers (M10.21–M10.30) ────────────
    if intelligence_router:
        app.include_router(intelligence_router.router)
    if planet_scale_router:
        app.include_router(planet_scale_router.router)
    if federation_router:
        app.include_router(federation_router.router)
    if evolution_router:
        app.include_router(evolution_router.router)
    if memory_v2_router:
        app.include_router(memory_v2_router.router)
    if router_v2_router:
        app.include_router(router_v2_router.router)
    if engineering_memory_router:
        app.include_router(engineering_memory_router.router)
    if error_intelligence_router:
        app.include_router(error_intelligence_router.router)
    if repository_router:
        app.include_router(repository_router.router)
    if workspace_v2_router:
        app.include_router(workspace_v2_router.router)

    # ── Milestone 10 Batch 4 routers (M10.31–M10.38) ────────────
    if reliability_router:
        app.include_router(reliability_router.router)
    if engineering_router:
        app.include_router(engineering_router.router)
    if engineering_extensions_router:
        app.include_router(engineering_extensions_router.router)
    if runtime_extensions_router:
        app.include_router(runtime_extensions_router.router)
    if project_dna_router:
        app.include_router(project_dna_router.router)
    if analytics_router:
        app.include_router(analytics_router.router)
    if cache_router:
        app.include_router(cache_router.router)
    if workflow_intelligence_router:
        app.include_router(workflow_intelligence_router.router)

    return app


app = create_app()
