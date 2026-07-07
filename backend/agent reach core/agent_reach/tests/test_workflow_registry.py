"""Unit tests for WorkflowRegistry (M5.3)."""

from __future__ import annotations

import pytest

from workflows.models import StepType, Workflow, WorkflowStep
from workflows.registry import WorkflowRegistry


def _make(name: str, version: str = "1.0") -> Workflow:
    return Workflow(
        name=name,
        version=version,
        steps=[
            WorkflowStep(
                step_id=f"{name}_s1",
                name=f"{name}_s1",
                type=StepType.TOOL,
                target="noop",
            )
        ],
    )


class TestWorkflowRegistryRegister:
    def test_register_returns_version_one(self) -> None:
        reg = WorkflowRegistry()
        v = reg.register(_make("greet"))
        assert v == 1

    def test_register_empty_name_raises(self) -> None:
        reg = WorkflowRegistry()
        with pytest.raises(ValueError, match="name must be non-empty"):
            reg.register(_make(""))

    def test_re_register_bumps_version(self) -> None:
        reg = WorkflowRegistry()
        reg.register(_make("greet"))
        reg.register(_make("greet"))
        v = reg.register(_make("greet"))
        assert v == 3
        assert reg.get_version("greet") == 3

    def test_register_replaces_workflow(self) -> None:
        reg = WorkflowRegistry()
        wf1 = _make("greet")
        wf2 = _make("greet", version="2.0")
        reg.register(wf1)
        reg.register(wf2)
        assert reg.get("greet") is wf2
        assert reg.get_version("greet") == 2


class TestWorkflowRegistryUnregister:
    def test_unregister_returns_true_when_present(self) -> None:
        reg = WorkflowRegistry()
        reg.register(_make("greet"))
        assert reg.unregister("greet") is True

    def test_unregister_returns_false_when_missing(self) -> None:
        reg = WorkflowRegistry()
        assert reg.unregister("missing") is False

    def test_unregister_removes_lookup(self) -> None:
        reg = WorkflowRegistry()
        wf = _make("greet")
        reg.register(wf)
        reg.unregister("greet")
        assert reg.get("greet") is None
        assert reg.get_by_id(wf.workflow_id) is None

    def test_unregister_keeps_version_counter(self) -> None:
        # Per design: re-registering after unregister continues from
        # the previous version number, not from 1.
        reg = WorkflowRegistry()
        reg.register(_make("greet"))
        reg.register(_make("greet"))
        reg.unregister("greet")
        v = reg.register(_make("greet"))
        assert v == 3


class TestWorkflowRegistryLookup:
    def test_get_returns_workflow(self) -> None:
        reg = WorkflowRegistry()
        wf = _make("greet")
        reg.register(wf)
        assert reg.get("greet") is wf

    def test_get_returns_none_when_missing(self) -> None:
        reg = WorkflowRegistry()
        assert reg.get("missing") is None

    def test_get_by_id(self) -> None:
        reg = WorkflowRegistry()
        wf = _make("greet")
        reg.register(wf)
        assert reg.get_by_id(wf.workflow_id) is wf

    def test_get_by_id_returns_none_when_missing(self) -> None:
        reg = WorkflowRegistry()
        assert reg.get_by_id("missing") is None

    def test_contains(self) -> None:
        reg = WorkflowRegistry()
        reg.register(_make("greet"))
        assert "greet" in reg
        assert "missing" not in reg

    def test_contains_non_string_is_false(self) -> None:
        reg = WorkflowRegistry()
        assert (123 in reg) is False  # type: ignore[operator]

    def test_len(self) -> None:
        reg = WorkflowRegistry()
        assert len(reg) == 0
        reg.register(_make("a"))
        reg.register(_make("b"))
        assert len(reg) == 2

    def test_list_names_sorted(self) -> None:
        reg = WorkflowRegistry()
        for n in ("z", "a", "m"):
            reg.register(_make(n))
        assert reg.list_names() == ["a", "m", "z"]

    def test_list_workflows_sorted(self) -> None:
        reg = WorkflowRegistry()
        for n in ("z", "a", "m"):
            reg.register(_make(n))
        wfs = reg.list_workflows()
        assert [w.name for w in wfs] == ["a", "m", "z"]


class TestWorkflowRegistryBulkLoad:
    def test_load_from(self) -> None:
        reg = WorkflowRegistry()
        versions = reg.load_from([_make("a"), _make("b"), _make("c")])
        assert versions == [1, 1, 1]
        assert len(reg) == 3


class TestWorkflowRegistryClear:
    def test_clear(self) -> None:
        reg = WorkflowRegistry()
        reg.register(_make("a"))
        reg.register(_make("b"))
        reg.clear()
        assert len(reg) == 0
        assert reg.list_names() == []
        # After clear, re-registering starts from version 1 again.
        v = reg.register(_make("a"))
        assert v == 1
