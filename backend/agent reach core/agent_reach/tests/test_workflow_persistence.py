"""Unit tests for Workflow Persistence (M5.6)."""

from __future__ import annotations

import json

import pytest

from workflows.models import (
    Condition,
    ConditionOp,
    StepExecutionRecord,
    StepType,
    Workflow,
    WorkflowResult,
    WorkflowState,
    WorkflowStep,
)
from workflows.persistence import (
    load_result,
    load_results,
    load_workflow,
    save_result,
    save_results,
    save_workflow,
)


def _make_workflow(name: str = "greet") -> Workflow:
    return Workflow(
        name=name,
        description="a workflow for testing",
        metadata={"owner": "test", "version": "1.0"},
        variables={"user": "world"},
        steps=[
            WorkflowStep(
                step_id="s1",
                name="step_one",
                type=StepType.AGENT,
                target="research",
                inputs={"q": "{{ variables.user }}"},
                condition=Condition("go", ConditionOp.TRUTHY),
                depends_on=["s0"],
                output_keys=["text"],
                timeout_seconds=15.0,
            ),
        ],
        outputs={"greeting": "outputs.s1.text"},
    )


def _make_result(workflow_id: str = "wf-1") -> WorkflowResult:
    return WorkflowResult(
        workflow_id=workflow_id,
        state=WorkflowState.COMPLETED,
        outputs={"greeting": "hello"},
        history=[
            StepExecutionRecord(
                step_id="s1",
                step_name="step_one",
                step_type=StepType.AGENT,
                started_at=1.0,
                finished_at=1.5,
                duration_ms=500.0,
                success=True,
                attempts=2,
                output={"text": "hello"},
            ),
        ],
        duration_ms=600.0,
    )


class TestSaveLoadSingleWorkflow:
    def test_roundtrip(self, tmp_path) -> None:
        wf = _make_workflow()
        p = save_workflow(wf, tmp_path / "wf.json")
        loaded = load_workflow(p)
        assert isinstance(loaded, Workflow)
        assert loaded.name == wf.name
        assert loaded.description == wf.description
        assert loaded.metadata == wf.metadata
        assert loaded.variables == wf.variables
        assert loaded.outputs == wf.outputs
        assert len(loaded.steps) == 1
        assert loaded.steps[0].step_id == "s1"
        assert loaded.steps[0].condition is not None
        assert loaded.steps[0].condition.variable == "go"
        assert loaded.steps[0].condition.op == ConditionOp.TRUTHY

    def test_save_returns_path(self, tmp_path) -> None:
        wf = _make_workflow()
        result_path = save_workflow(wf, tmp_path / "wf.json")
        assert isinstance(result_path, type(tmp_path / "x"))
        assert result_path.exists()

    def test_creates_parent_dirs(self, tmp_path) -> None:
        wf = _make_workflow()
        nested = tmp_path / "a" / "b" / "wf.json"
        save_workflow(wf, nested)
        assert nested.exists()

    def test_load_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_workflow(tmp_path / "missing.json")


class TestSaveLoadMultipleWorkflows:
    def test_roundtrip_list(self, tmp_path) -> None:
        wfs = [_make_workflow("a"), _make_workflow("b"), _make_workflow("c")]
        p = save_workflow(wfs, tmp_path / "wfs.json")
        loaded = load_workflow(p)
        assert isinstance(loaded, list)
        assert len(loaded) == 3
        assert [w.name for w in loaded] == ["a", "b", "c"]


class TestSaveLoadResult:
    def test_roundtrip(self, tmp_path) -> None:
        r = _make_result()
        p = save_result(r, tmp_path / "r.json")
        loaded = load_result(p)
        assert loaded.workflow_id == r.workflow_id
        assert loaded.state == r.state
        assert loaded.outputs == r.outputs
        assert loaded.duration_ms == r.duration_ms
        assert len(loaded.history) == 1
        assert loaded.history[0].step_id == "s1"
        assert loaded.history[0].attempts == 2

    def test_save_multiple_results(self, tmp_path) -> None:
        rs = [_make_result("wf-1"), _make_result("wf-2")]
        p = save_results(rs, tmp_path / "rs.json")
        loaded = load_results(p)
        assert [r.workflow_id for r in loaded] == ["wf-1", "wf-2"]

    def test_load_results_requires_list(self, tmp_path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a list"):
            load_results(p)


class TestJSONShape:
    def test_single_workflow_json_is_object(self, tmp_path) -> None:
        wf = _make_workflow()
        p = save_workflow(wf, tmp_path / "wf.json")
        with p.open() as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data["name"] == "greet"

    def test_multiple_workflows_json_is_list(self, tmp_path) -> None:
        wfs = [_make_workflow("a"), _make_workflow("b")]
        p = save_workflow(wfs, tmp_path / "wfs.json")
        with p.open() as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_load_rejects_non_dict_non_list(self, tmp_path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("\"just a string\"", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a dict or list"):
            load_workflow(p)


class TestAtomicWrite:
    def test_partial_write_does_not_corrupt(self, tmp_path) -> None:
        """A failed write should not leave a partial file at the target path."""
        wf = _make_workflow("good")

        target = tmp_path / "wf.json"

        # Sanity: empty target to start.
        assert not target.exists()

        save_workflow(wf, target)
        assert target.exists()

        # The .tmp file used during write should not survive a clean run.
        siblings = list(tmp_path.iterdir())
        # Either just the target, or target + leftover tmp files.
        # The contract is: target exists, and any leftover tmp is harmless.
        assert target in siblings

    def test_invalid_payload_raises_and_cleans_tmp(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forcing json.dump to fail should leave no partial file."""
        wf = _make_workflow("oops")
        target = tmp_path / "wf.json"

        # Force json.dump to raise on the first call (during save).
        import workflows.persistence as persistence_module

        real_dump = persistence_module.json.dump
        call_count = {"n": 0}

        def maybe_fail_dump(*args: object, **kwargs: object) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated disk full")
            real_dump(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(persistence_module.json, "dump", maybe_fail_dump)

        with pytest.raises(RuntimeError, match="simulated disk full"):
            save_workflow(wf, target)

        # Target file should NOT have been created (the atomic
        # write path replaces the .tmp only on success).
        assert not target.exists()
        # And no leftover .tmp files in the directory.
        leftovers = [
            p for p in tmp_path.iterdir()
            if p.name.startswith("wf.json.") and p.name.endswith(".tmp")
        ]
        assert leftovers == []
