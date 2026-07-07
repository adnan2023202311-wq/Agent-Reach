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
# Milestone 8 routers
try:
    from api.routers import memory as memory_router
except Exception:
    memory_router = None
try:
    from api.routers import knowledge as knowledge_router
except Exception:
    knowledge_router = None
try:
    from api.routers import prompts_studio as prompts_router
except Exception:
    prompts_router = None
try:
    from api.routers import observatory as observatory_router
except Exception:
    observatory_router = None
try:
    from api.routers import skills as skills_router
except Exception:
    skills_router = None
from composition import (
    build_default_controller,
    build_conversation_engine,
    build_intelligent_pipeline,
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
        # Build the M7.5 intelligent pipeline (recommended entry point)
        app.state.pipeline = build_intelligent_pipeline(settings)
        # Build M6 components.
        app.state.conversation_engine = build_conversation_engine(settings)
        app.state.session_manager = app.state.conversation_engine._session_manager
        app.state.workflow_engine = build_workflow_engine(settings)
        app.state.workflow_registry = build_workflow_registry()
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

    return app


app = create_app()
