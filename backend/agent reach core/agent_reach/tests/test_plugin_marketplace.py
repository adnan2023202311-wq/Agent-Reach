"""Unit tests for PluginMarketplace (M6.9)."""

from __future__ import annotations

import pytest

from marketplace import (
    PluginInstallStatus,
    PluginMarketplace,
    PluginMarketplaceMetadata,
)


def _make_metadata(
    plugin_id: str = "test-plugin",
    name: str = "Test Plugin",
    version: str = "1.0.0",
    status: PluginInstallStatus = PluginInstallStatus.AVAILABLE,
    **kwargs: object,
) -> PluginMarketplaceMetadata:
    return PluginMarketplaceMetadata(
        plugin_id=plugin_id,
        name=name,
        version=version,
        status=status,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def marketplace() -> PluginMarketplace:
    return PluginMarketplace(platform_version="1.0.0")


# ---------------------------------------------------------------------------
# Metadata registration
# ---------------------------------------------------------------------------


class TestMetadataRegistration:
    def test_register_metadata(self, marketplace: PluginMarketplace) -> None:
        meta = _make_metadata()
        result = marketplace.register_metadata(meta)
        assert result.plugin_id == "test-plugin"
        assert result.status == PluginInstallStatus.AVAILABLE

    def test_register_preserves_installed_status(self, marketplace: PluginMarketplace) -> None:
        meta = _make_metadata(status=PluginInstallStatus.INSTALLED, installed_at="2024-01-01")
        marketplace.register_metadata(meta)
        # Re-register with same version — status should stay INSTALLED.
        meta2 = _make_metadata(status=PluginInstallStatus.AVAILABLE)
        result = marketplace.register_metadata(meta2)
        assert result.status == PluginInstallStatus.INSTALLED
        assert result.installed_at == "2024-01-01"

    def test_register_detects_update(self, marketplace: PluginMarketplace) -> None:
        meta = _make_metadata(version="1.0.0", status=PluginInstallStatus.INSTALLED)
        marketplace.register_metadata(meta)
        # Re-register with new version — should become UPDATE_AVAILABLE.
        meta2 = _make_metadata(version="2.0.0")
        result = marketplace.register_metadata(meta2)
        assert result.status == PluginInstallStatus.UPDATE_AVAILABLE

    def test_unregister_metadata(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata())
        assert marketplace.unregister_metadata("test-plugin") is True
        assert marketplace.get("test-plugin") is None

    def test_unregister_missing(self, marketplace: PluginMarketplace) -> None:
        assert marketplace.unregister_metadata("ghost") is False


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


class TestInstallation:
    def test_install(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata())
        result = marketplace.install("test-plugin")
        assert result is not None
        assert result.status == PluginInstallStatus.INSTALLED
        assert result.installed_at

    def test_install_missing(self, marketplace: PluginMarketplace) -> None:
        assert marketplace.install("ghost") is None

    def test_uninstall(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata())
        marketplace.install("test-plugin")
        result = marketplace.uninstall("test-plugin")
        assert result is not None
        assert result.status == PluginInstallStatus.AVAILABLE
        assert result.installed_at == ""

    def test_uninstall_missing(self, marketplace: PluginMarketplace) -> None:
        assert marketplace.uninstall("ghost") is None


# ---------------------------------------------------------------------------
# Compatibility validation
# ---------------------------------------------------------------------------


class TestCompatibility:
    def test_compatible_plugin(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(min_platform_version="1.0.0")
        )
        compatible, issues = marketplace.check_compatibility("test-plugin")
        assert compatible is True
        assert issues == []

    def test_incompatible_plugin(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(min_platform_version="2.0.0")
        )
        compatible, issues = marketplace.check_compatibility("test-plugin")
        assert compatible is False
        assert len(issues) == 1
        assert "requires platform version" in issues[0]

    def test_compatibility_missing_plugin(self, marketplace: PluginMarketplace) -> None:
        compatible, issues = marketplace.check_compatibility("ghost")
        assert compatible is False
        assert "not registered" in issues[0]

    def test_validate_all(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="ok", min_platform_version="1.0.0")
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="bad", min_platform_version="99.0.0")
        )
        issues = marketplace.validate_all()
        assert "ok" not in issues
        assert "bad" in issues


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------


class TestVersionManagement:
    def test_check_for_updates(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="p1", status=PluginInstallStatus.INSTALLED)
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="p2", status=PluginInstallStatus.UPDATE_AVAILABLE)
        )
        updates = marketplace.check_for_updates()
        assert [m.plugin_id for m in updates] == ["p2"]

    def test_mark_update_available(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="p1", version="1.0.0", status=PluginInstallStatus.INSTALLED)
        )
        result = marketplace.mark_update_available("p1", "2.0.0")
        assert result is not None
        assert result.version == "2.0.0"
        assert result.status == PluginInstallStatus.UPDATE_AVAILABLE

    def test_mark_update_missing(self, marketplace: PluginMarketplace) -> None:
        assert marketplace.mark_update_available("ghost", "2.0.0") is None

    def test_version_satisfies(self) -> None:
        assert PluginMarketplace._version_satisfies("1.0.0", "1.0.0") is True
        assert PluginMarketplace._version_satisfies("2.0.0", "1.0.0") is True
        assert PluginMarketplace._version_satisfies("1.0.0", "2.0.0") is False
        assert PluginMarketplace._version_satisfies("1.2.3", "1.2.0") is True
        assert PluginMarketplace._version_satisfies("1.2.3", "1.3.0") is False

    def test_version_satisfies_with_prerelease(self) -> None:
        # Pre-release metadata is stripped for comparison.
        assert PluginMarketplace._version_satisfies("1.0.0-rc1", "1.0.0") is True


# ---------------------------------------------------------------------------
# Access and listing
# ---------------------------------------------------------------------------


class TestAccess:
    def test_get(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata())
        meta = marketplace.get("test-plugin")
        assert meta is not None
        assert meta.name == "Test Plugin"

    def test_get_missing(self, marketplace: PluginMarketplace) -> None:
        assert marketplace.get("ghost") is None

    def test_list_plugins(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata(plugin_id="a", name="Alpha"))
        marketplace.register_metadata(_make_metadata(plugin_id="b", name="Beta"))
        results = marketplace.list_plugins()
        assert [m.plugin_id for m in results] == ["a", "b"]

    def test_list_plugins_by_status(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", status=PluginInstallStatus.INSTALLED)
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", status=PluginInstallStatus.AVAILABLE)
        )
        installed = marketplace.list_plugins(status=PluginInstallStatus.INSTALLED)
        assert [m.plugin_id for m in installed] == ["a"]

    def test_list_plugins_by_type(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", plugin_type="agent")
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", plugin_type="tool")
        )
        agents = marketplace.list_plugins(plugin_type="agent")
        assert [m.plugin_id for m in agents] == ["a"]

    def test_list_plugins_by_tag(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", tags=["web"])
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", tags=["local"])
        )
        web = marketplace.list_plugins(tag="web")
        assert [m.plugin_id for m in web] == ["a"]

    def test_list_installed(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", status=PluginInstallStatus.INSTALLED)
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", status=PluginInstallStatus.AVAILABLE)
        )
        installed = marketplace.list_installed()
        assert [m.plugin_id for m in installed] == ["a"]

    def test_search(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", name="Web Scraper", description="Scrapes web pages")
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", name="Local File", description="Reads files")
        )
        results = marketplace.search("scrape")
        assert [m.plugin_id for m in results] == ["a"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats_empty(self, marketplace: PluginMarketplace) -> None:
        stats = marketplace.get_stats()
        assert stats == {
            "total": 0,
            "installed": 0,
            "available": 0,
            "updates_available": 0,
        }

    def test_get_stats_populated(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(
            _make_metadata(plugin_id="a", status=PluginInstallStatus.INSTALLED)
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="b", status=PluginInstallStatus.AVAILABLE)
        )
        marketplace.register_metadata(
            _make_metadata(plugin_id="c", status=PluginInstallStatus.UPDATE_AVAILABLE)
        )
        stats = marketplace.get_stats()
        assert stats["total"] == 3
        assert stats["installed"] == 1
        assert stats["available"] == 1
        assert stats["updates_available"] == 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_metadata_to_dict(self) -> None:
        meta = _make_metadata(
            plugin_id="p1",
            name="Test",
            version="1.2.3",
            tags=["a", "b"],
        )
        d = meta.to_dict()
        assert d["plugin_id"] == "p1"
        assert d["name"] == "Test"
        assert d["version"] == "1.2.3"
        assert d["tags"] == ["a", "b"]
        assert d["status"] == "available"

    def test_metadata_from_dict(self) -> None:
        data = {
            "plugin_id": "p1",
            "name": "Test",
            "version": "1.0.0",
            "status": "installed",
            "tags": ["a"],
        }
        meta = PluginMarketplaceMetadata.from_dict(data)
        assert meta.plugin_id == "p1"
        assert meta.status == PluginInstallStatus.INSTALLED


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear(self, marketplace: PluginMarketplace) -> None:
        marketplace.register_metadata(_make_metadata(plugin_id="a"))
        marketplace.register_metadata(_make_metadata(plugin_id="b"))
        marketplace.clear()
        assert marketplace.list_plugins() == []
