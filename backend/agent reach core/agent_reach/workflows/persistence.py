"""
Workflow & Orchestration Layer — JSON Persistence (M5.6).

Layer: Application/Core — depends inward on domain/ only.

JSON-only persistence for Workflow definitions and execution
results. Per the M5 specification:

> JSON storage only.
> No database.

Two top-level helpers:
- :func:`save_workflow` / :func:`load_workflow` — single Workflow
  definition (or list of them) to/from a JSON file.
- :func:`save_result` / :func:`load_result` — a single
  :class:`~workflows.models.WorkflowResult` (the execution
  history of one run).

Why a thin wrapper around ``json`` instead of ``pickle``:
- Workflow definitions are author-facing and should be diff-able,
  reviewable, and editable. JSON wins on all three counts.
- ``pickle`` is not safe across versions and ties persistence to
  the exact class layout.
- ``Workflow.to_dict()`` / :meth:`Workflow.from_dict` already
  produce JSON-friendly structures, so the layer here is just
  ``json.dump`` / ``json.load`` plus atomic-file-write hygiene.

Atomic file writes (``save_*`` writes to a sibling ``.tmp`` and
then ``os.replace``) ensure a partially-written file never appears
on disk — important because workflows are persistent state the
system relies on at restart.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union

from workflows.models import Workflow, WorkflowResult


# A type alias for "either a single workflow or a list of workflows".
WorkflowOrList = Union[Workflow, list[Workflow]]


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write ``payload`` as JSON to ``path`` atomically.

    Writes to a sibling ``.tmp`` file first and then ``os.replace``
    so a reader never sees a partially-written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        # Clean up the partial temp file on failure so we don't
        # leave litter in the directory.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_workflow(workflow: WorkflowOrList, path: Union[str, Path]) -> Path:
    """Save one Workflow or a list of Workflows to a JSON file.

    Returns the resolved path as a :class:`pathlib.Path`.
    """
    p = Path(path)
    if isinstance(workflow, list):
        payload = [w.to_dict() for w in workflow]
    else:
        payload = workflow.to_dict()
    _atomic_write_json(p, payload)
    return p


def load_workflow(path: Union[str, Path]) -> Union[Workflow, list[Workflow]]:
    """Load one Workflow or a list of Workflows from a JSON file.

    The shape is detected from the top-level JSON value:
    - A dict is treated as a single Workflow.
    - A list is treated as a list of Workflows.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the JSON is malformed or its shape is neither
            a dict nor a list.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return [Workflow.from_dict(item) for item in data]
    if isinstance(data, dict):
        return Workflow.from_dict(data)
    raise ValueError(
        f"Workflow JSON must be a dict or list, got {type(data).__name__}"
    )


def save_result(result: WorkflowResult, path: Union[str, Path]) -> Path:
    """Save a WorkflowResult (one execution history) to a JSON file."""
    p = Path(path)
    _atomic_write_json(p, result.to_dict())
    return p


def load_result(path: Union[str, Path]) -> WorkflowResult:
    """Load a WorkflowResult from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Result file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return WorkflowResult.from_dict(data)


def save_results(results: list[WorkflowResult], path: Union[str, Path]) -> Path:
    """Save multiple WorkflowResults to a JSON file as a list."""
    p = Path(path)
    _atomic_write_json(p, [r.to_dict() for r in results])
    return p


def load_results(path: Union[str, Path]) -> list[WorkflowResult]:
    """Load multiple WorkflowResults from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Results file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Results JSON must be a list, got {type(data).__name__}"
        )
    return [WorkflowResult.from_dict(item) for item in data]


__all__ = [
    "WorkflowOrList",
    "load_result",
    "load_results",
    "load_workflow",
    "save_result",
    "save_results",
    "save_workflow",
]
