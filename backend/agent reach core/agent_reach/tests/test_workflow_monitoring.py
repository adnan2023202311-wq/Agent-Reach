"""Unit tests for WorkflowMonitor (M5.8)."""

from __future__ import annotations

import pytest

from workflows.models import (
    StepExecutionRecord,
    StepType,
    WorkflowResult,
    WorkflowState,
)
from workflows.monitoring import WorkflowMonitor, WorkflowStats


def _make_result(
    workflow_id: str = "wf-1",
    state: WorkflowState = WorkflowState.COMPLETED,
    duration_ms: float = 100.0,
    error: str | None = None,
) -> WorkflowResult:
    return WorkflowResult(
        workflow_id=workflow_id,
        state=state,
        outputs={},
        history=[
            StepExecutionRecord(
                step_id="s1",
                step_name="S1",
                step_type=StepType.AGENT,
                started_at=0.0,
                finished_at=duration_ms / 1000.0,
                duration_ms=duration_ms,
                success=(state == WorkflowState.COMPLETED),
                error=error,
            )
        ],
        duration_ms=duration_ms,
        error=error,
    )


class TestWorkflowMonitorRecording:
    def test_record_appends(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result())
        assert m.get_results()[0].workflow_id == "wf-1"

    def test_record_multiple(self) -> None:
        m = WorkflowMonitor()
        for i in range(3):
            m.record(_make_result(workflow_id=f"wf-{i}"))
        assert len(m.get_results()) == 3

    def test_record_drops_from_active(self) -> None:
        m = WorkflowMonitor()
        m.mark_active("wf-1")
        m.record(_make_result(workflow_id="wf-1"))
        assert "wf-1" not in m.get_active()

    def test_clear(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result())
        m.mark_active("wf-x")
        m.clear()
        assert m.get_results() == []
        assert m.get_active() == []


class TestWorkflowMonitorActive:
    def test_mark_active(self) -> None:
        m = WorkflowMonitor()
        m.mark_active("wf-1")
        assert m.get_active() == ["wf-1"]

    def test_mark_active_multiple(self) -> None:
        m = WorkflowMonitor()
        m.mark_active("wf-1")
        m.mark_active("wf-2")
        m.mark_active("wf-3")
        assert m.get_active() == ["wf-1", "wf-2", "wf-3"]

    def test_mark_done(self) -> None:
        m = WorkflowMonitor()
        m.mark_active("wf-1")
        m.mark_active("wf-2")
        m.mark_done("wf-1")
        assert m.get_active() == ["wf-2"]

    def test_mark_done_missing_is_safe(self) -> None:
        m = WorkflowMonitor()
        m.mark_done("never-active")  # should not raise
        assert m.get_active() == []


class TestWorkflowMonitorGetStats:
    def test_empty_monitor(self) -> None:
        m = WorkflowMonitor()
        stats = m.get_stats()
        assert stats == WorkflowStats()

    def test_total_count(self) -> None:
        m = WorkflowMonitor()
        for i in range(5):
            m.record(_make_result(workflow_id=f"wf-{i}"))
        stats = m.get_stats()
        assert stats.total == 5

    def test_completed_count(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(state=WorkflowState.COMPLETED))
        m.record(_make_result(state=WorkflowState.COMPLETED))
        m.record(_make_result(state=WorkflowState.FAILED))
        stats = m.get_stats()
        assert stats.completed == 2
        assert stats.failed == 1
        assert stats.cancelled == 0

    def test_cancelled_count(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(state=WorkflowState.CANCELLED))
        stats = m.get_stats()
        assert stats.cancelled == 1

    def test_active_count(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result())  # not active anymore
        m.mark_active("wf-running-1")
        m.mark_active("wf-running-2")
        stats = m.get_stats()
        assert stats.active == 2

    def test_durations(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(duration_ms=100.0))
        m.record(_make_result(duration_ms=200.0))
        m.record(_make_result(duration_ms=400.0))
        stats = m.get_stats()
        assert stats.average_duration_ms == 233.33333333333334
        assert stats.median_duration_ms == 200.0
        assert stats.min_duration_ms == 100.0
        assert stats.max_duration_ms == 400.0

    def test_durations_single_value(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(duration_ms=123.0))
        stats = m.get_stats()
        assert stats.average_duration_ms == 123.0
        assert stats.median_duration_ms == 123.0

    def test_by_workflow(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(workflow_id="wf-a"))
        m.record(_make_result(workflow_id="wf-a"))
        m.record(_make_result(workflow_id="wf-b"))
        stats = m.get_stats()
        assert stats.by_workflow == {"wf-a": 2, "wf-b": 1}


class TestWorkflowMonitorFilters:
    def test_get_failures(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(state=WorkflowState.COMPLETED))
        m.record(_make_result(state=WorkflowState.FAILED, error="boom"))
        failures = m.get_failures()
        assert len(failures) == 1
        assert failures[0].error == "boom"

    def test_get_completed(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(state=WorkflowState.COMPLETED))
        m.record(_make_result(state=WorkflowState.FAILED))
        completed = m.get_completed()
        assert len(completed) == 1
        assert completed[0].state == WorkflowState.COMPLETED

    def test_get_results_filter_by_state(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(state=WorkflowState.COMPLETED, workflow_id="a"))
        m.record(_make_result(state=WorkflowState.FAILED, workflow_id="b"))
        assert len(m.get_results(state=WorkflowState.COMPLETED)) == 1
        assert len(m.get_results(state=WorkflowState.FAILED)) == 1

    def test_get_results_filter_by_workflow_id(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(workflow_id="wf-a"))
        m.record(_make_result(workflow_id="wf-a"))
        m.record(_make_result(workflow_id="wf-b"))
        assert len(m.get_results(workflow_id="wf-a")) == 2
        assert len(m.get_results(workflow_id="wf-b")) == 1

    def test_get_results_filter_combined(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(workflow_id="a", state=WorkflowState.COMPLETED))
        m.record(_make_result(workflow_id="a", state=WorkflowState.FAILED))
        m.record(_make_result(workflow_id="b", state=WorkflowState.COMPLETED))
        assert (
            len(m.get_results(workflow_id="a", state=WorkflowState.COMPLETED))
            == 1
        )

    def test_get_durations_returns_list(self) -> None:
        m = WorkflowMonitor()
        m.record(_make_result(duration_ms=50.0))
        m.record(_make_result(duration_ms=75.0))
        assert m.get_durations() == [50.0, 75.0]
