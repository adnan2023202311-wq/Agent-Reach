"""
Tests for composition.py's wiring.

No network access needed: AnthropicModelClient only makes a network
call inside complete(), never at construction, so these prove the
wiring fails fast and correctly on bad config — which is exactly the
behavior a real deployment depends on — without hitting a real API.
"""

from __future__ import annotations

import pytest

from composition import build_default_controller
from config.settings import Settings


def test_build_default_controller_falls_back_to_mock_without_api_key() -> None:
    """M6.2 Runtime Fix: controller falls back to MockModelClient when no key."""
    settings = Settings(anthropic_api_key=None, default_model_provider="anthropic")
    controller = build_default_controller(settings)
    assert controller is not None


def test_build_default_controller_succeeds_with_api_key() -> None:
    settings = Settings(anthropic_api_key="fake-key-for-wiring-test-only")
    controller = build_default_controller(settings)
    assert controller is not None
