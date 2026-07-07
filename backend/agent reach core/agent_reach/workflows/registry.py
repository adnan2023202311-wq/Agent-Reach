"""
Workflow & Orchestration Layer — WorkflowRegistry (M5.3).

Layer: Application/Core — depends inward on domain/ only.

A simple in-memory registry for named Workflow definitions.
Workflows are looked up by their unique ``workflow_id`` and by
their (uniquely-named) ``name``. The registry also keeps a version
counter per name so callers can detect when a workflow has been
re-registered.

The registry deliberately does NOT execute workflows — execution
belongs to :class:`~workflows.engine.WorkflowEngine`. It is
purely a lookup table, which keeps the responsibilities clean
and makes the registry trivial to persist or replicate later.

Design notes
------------
- Lookups are O(1) via two dicts: ``_by_id`` and ``_by_name``.
- Re-registering an existing name replaces the old workflow AND
  bumps its version counter. The version is monotonic per name
  (not global) so callers can tell "this is the third version of
  workflow 'greet'" rather than just "this is version 7 of
  something".
- ``unregister`` returns False when the name is unknown, which
  matches the M3 AgentMessenger / M4 Scheduler convention.
"""

from __future__ import annotations

import time
from typing import Optional

from workflows.models import Workflow


class WorkflowRegistry:
    """In-memory registry of named Workflow definitions."""

    def __init__(self) -> None:
        self._by_id: dict[str, Workflow] = {}
        self._by_name: dict[str, Workflow] = {}
        self._versions: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, workflow: Workflow) -> int:
        """Register or replace a Workflow by its ``name``.

        Returns the new version number (1-based, per name).
        """
        if not workflow.name:
            raise ValueError("Workflow.name must be non-empty to register")

        self._by_id[workflow.workflow_id] = workflow
        self._by_name[workflow.name] = workflow
        self._versions[workflow.name] = self._versions.get(workflow.name, 0) + 1
        return self._versions[workflow.name]

    def unregister(self, name: str) -> bool:
        """Remove the Workflow with the given ``name``.

        Returns True if a workflow was removed, False if ``name``
        was unknown.
        """
        wf = self._by_name.pop(name, None)
        if wf is None:
            return False
        self._by_id.pop(wf.workflow_id, None)
        # Keep the version counter — it is monotonic per name even
        # after a workflow is unregistered and later re-registered.
        return True

    def clear(self) -> None:
        """Remove every Workflow. Useful for testing."""
        self._by_id.clear()
        self._by_name.clear()
        self._versions.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Workflow]:
        """Return the Workflow with the given ``name`` or None."""
        return self._by_name.get(name)

    def get_by_id(self, workflow_id: str) -> Optional[Workflow]:
        """Return the Workflow with the given ``workflow_id`` or None."""
        return self._by_id.get(workflow_id)

    def get_version(self, name: str) -> int:
        """Return the current version for ``name`` (0 if unregistered)."""
        return self._versions.get(name, 0)

    def list_names(self) -> list[str]:
        """Return all registered names, sorted alphabetically."""
        return sorted(self._by_name.keys())

    def list_workflows(self) -> list[Workflow]:
        """Return all registered Workflows, sorted by name."""
        return [self._by_name[name] for name in self.list_names()]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    def load_from(self, workflows: list[Workflow]) -> list[int]:
        """Bulk-register a list of Workflows, returning their versions.

        Convenience method used by the M5.6 persistence layer when
        loading a JSON file containing multiple workflow definitions.
        """
        return [self.register(wf) for wf in workflows]


__all__ = ["WorkflowRegistry"]
