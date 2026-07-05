"""
API layer: FastAPI application factory.

Layer: Interface/Presentation (outermost besides composition.py).

This is intentionally the only module that imports FastAPI, builds the
app, and triggers the composition root — every other module in the
codebase can be imported and unit-tested without a running web server.
The MainController is built inside `lifespan`, at actual server
startup, not at import time — a router that builds a `MainController()`
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
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.exception_handlers import register_exception_handlers
from api.routers import agents, chat, dashboard, health, providers, tools
from composition import build_default_controller
from config.logging_config import configure_logging
from config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.controller = build_default_controller(settings)
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
    app.include_router(agents.router)
    app.include_router(tools.router)
    app.include_router(providers.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
