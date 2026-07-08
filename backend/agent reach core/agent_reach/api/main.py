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

    return app


app = create_app()
