"""
Tests for the Dynamic Plugin Loader.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest

from agent_reach.core.plugin.dynamic_loader import DynamicPluginLoader


def test_discover_empty_directory() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = DynamicPluginLoader(tmpdir)
        plugins = asyncio.run(loader.discover())
        assert plugins == []


def test_discover_nonexistent_directory() -> None:
    loader = DynamicPluginLoader("/nonexistent/path")
    plugins = asyncio.run(loader.discover())
    assert plugins == []


def test_discover_valid_plugins() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "research_agent")
        os.makedirs(plugin_dir)
        manifest = {
            "id": "agent.research.v1",
            "name": "Research Agent",
            "version": "1.0.0",
            "description": "Agent for researching",
            "type": "agent",
            "author": "Test",
            "capabilities": ["search"],
            "entry_point": "agent_reach.agents.research:ResearchAgent",
        }
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump(manifest, f)

        loader = DynamicPluginLoader(tmpdir)
        plugins = asyncio.run(loader.discover())
        assert "agent.research.v1" in plugins


def test_discover_skips_invalid_manifests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "bad_plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            f.write("not valid json")

        loader = DynamicPluginLoader(tmpdir)
        plugins = asyncio.run(loader.discover())
        assert plugins == []


def test_discover_skips_directories_without_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "empty_dir"))

        loader = DynamicPluginLoader(tmpdir)
        plugins = asyncio.run(loader.discover())
        assert plugins == []


def test_load_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "research_agent")
        os.makedirs(plugin_dir)
        manifest = {
            "id": "agent.research.v1",
            "name": "Research Agent",
            "version": "1.0.0",
            "description": "Agent for researching",
            "type": "agent",
        }
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump(manifest, f)

        loader = DynamicPluginLoader(tmpdir)
        asyncio.run(loader.discover())

        loaded = asyncio.run(loader.load_manifest("agent.research.v1"))
        assert loaded is not None
        assert loaded.id == "agent.research.v1"
        assert loaded.name == "Research Agent"


def test_unload_plugin() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "research_agent")
        os.makedirs(plugin_dir)
        manifest = {
            "id": "agent.research.v1",
            "name": "Research Agent",
            "version": "1.0.0",
            "description": "Agent for researching",
            "type": "agent",
        }
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump(manifest, f)

        loader = DynamicPluginLoader(tmpdir)
        asyncio.run(loader.discover())

        result = asyncio.run(loader.unload_plugin("agent.research.v1"))
        assert result is True
        assert asyncio.run(loader.load_manifest("agent.research.v1")) is None


def test_unload_plugin_not_found() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = DynamicPluginLoader(tmpdir)
        result = asyncio.run(loader.unload_plugin("nonexistent"))
        assert result is False
