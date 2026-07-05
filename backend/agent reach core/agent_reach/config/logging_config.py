"""
Config layer: centralized logging setup.

Layer: Config/Infrastructure.

Kept separate from api/main.py so any entrypoint — the FastAPI app, a
future CLI or background worker, or a test harness — configures
logging identically by calling configure_logging() once at startup,
instead of logging configuration being a side effect of importing the
web app module (which is what the previous version did).
"""

from __future__ import annotations

import logging

from config.settings import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
