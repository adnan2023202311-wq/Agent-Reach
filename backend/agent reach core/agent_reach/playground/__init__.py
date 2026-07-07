"""
Playground layer: Developer Playground (M6.7).

Layer: Application/Core — depends inward on all layers.

Provides a developer playground for inspecting and debugging the
Agent-Reach platform. The playground wraps the existing components
with inspection capabilities:

- **execute workflows**: run a workflow and inspect the result
- **inspect planner output**: see what plan the planner produces
  for a given request
- **inspect runtime**: view active sessions and their states
- **inspect memory**: view memory layer contents
- **inspect execution history**: view past execution results

The playground is a developer tool, not a production API. It is
designed to be used interactively (e.g., in a Jupyter notebook or
a CLI) to understand how the system behaves.

Design notes
------------
- The playground does NOT add new functionality — it provides
  inspection methods on top of existing components.
- All inspection methods return plain data (dicts, lists) that
  can be printed or serialized.
- The playground is stateless — it holds references to the
  components but does not maintain its own state.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Playground:
    """Developer playground for inspecting Agent-Reach.

    Parameters
    ----------
    controller:
        The MainController instance.
    conversation_engine:
        Optional ConversationEngine for session/conversation inspection.
    workflow_engine:
        Optional WorkflowEngine for workflow execution.
    workflow_registry:
        Optional WorkflowRegistry for workflow listing.
    """

    def __init__(
        self,
        controller: Any,
        conversation_engine: Any = None,
        workflow_engine: Any = None,
        workflow_registry: Any = None,
    ) -> None:
        self._controller = controller
        self._conversation_engine = conversation_engine
        self._workflow_engine = workflow_engine
        self._workflow_registry = workflow_registry

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------

    def execute_workflow(
        self,
        workflow: Any,
        variables: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a workflow and return the full result as a dict.

        Parameters
        ----------
        workflow:
            A Workflow instance.
        variables:
            Optional initial variable overrides.

        Returns
        -------
        dict with the workflow result (state, outputs, history, etc.)
        """
        if self._workflow_engine is None:
            raise RuntimeError("WorkflowEngine not available")
        result = self._workflow_engine.run_sync(workflow, variables)
        return result.to_dict()

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all registered workflows."""
        if self._workflow_registry is None:
            return []
        return [
            {
                "name": wf.name,
                "description": wf.description,
                "version": wf.version,
                "step_count": len(wf.steps),
            }
            for wf in self._workflow_registry.list_workflows()
        ]

    # ------------------------------------------------------------------
    # Planner inspection
    # ------------------------------------------------------------------

    def inspect_plan(self, request: str) -> dict[str, Any]:
        """Inspect the plan the planner produces for a request.

        Parameters
        ----------
        request:
            The user request to plan.

        Returns
        -------
        dict with the plan details (id, request, subtasks).
        """
        import asyncio

        planner = self._controller._planner
        plan = asyncio.run(planner.create_plan(request))
        return {
            "plan_id": plan.id,
            "original_request": plan.original_request,
            "created_at": plan.created_at.isoformat(),
            "subtask_count": len(plan.subtasks),
            "subtasks": [
                {
                    "id": st.id,
                    "agent_type": st.agent_type.value,
                    "description": st.description,
                    "input_data": st.input_data,
                    "depends_on": st.depends_on,
                }
                for st in plan.subtasks
            ],
        }

    # ------------------------------------------------------------------
    # Runtime inspection
    # ------------------------------------------------------------------

    def inspect_runtime(self) -> dict[str, Any]:
        """Inspect the current runtime state.

        Returns
        -------
        dict with runtime information (registered agents, etc.)
        """
        agent_types = self._controller.registered_agent_types()
        return {
            "registered_agents": [at.value for at in agent_types],
            "agent_count": len(agent_types),
        }

    def inspect_sessions(self, user_id: str = "") -> list[dict[str, Any]]:
        """Inspect active sessions.

        Parameters
        ----------
        user_id:
            Optional user ID filter.

        Returns
        -------
        list of session dicts.
        """
        if self._conversation_engine is None:
            return []
        sessions = self._conversation_engine._session_manager.list_sessions(
            user_id=user_id
        )
        return [
            {
                "session_id": s.session_id,
                "user_id": s.user_id,
                "state": s.state.value,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ]

    # ------------------------------------------------------------------
    # Memory inspection
    # ------------------------------------------------------------------

    def inspect_memory(self, session_id: str = "") -> dict[str, Any]:
        """Inspect conversation memory/context.

        Parameters
        ----------
        session_id:
            Optional session ID to inspect. If empty, returns summary.

        Returns
        -------
        dict with memory information.
        """
        if self._conversation_engine is None:
            return {"available": False}

        if session_id:
            history = self._conversation_engine.get_history(session_id)
            context = self._conversation_engine.get_context(session_id)
            return {
                "session_id": session_id,
                "message_count": len(history),
                "context": context,
                "messages": [m.to_dict() for m in history],
            }

        # Summary: count sessions.
        sessions = self._conversation_engine._session_manager.list_sessions()
        return {
            "session_count": len(sessions),
            "sessions": [s.session_id for s in sessions],
        }

    # ------------------------------------------------------------------
    # Execution history inspection
    # ------------------------------------------------------------------

    def inspect_execution_history(self) -> list[dict[str, Any]]:
        """Inspect workflow execution history.

        Returns
        -------
        list of workflow result dicts.
        """
        if self._workflow_engine is None:
            return []
        return [r.to_dict() for r in self._workflow_engine.list_results()]

    def get_execution_result(self, workflow_id: str) -> Optional[dict[str, Any]]:
        """Get a specific execution result by workflow_id.

        Returns
        -------
        dict with the result, or None if not found.
        """
        if self._workflow_engine is None:
            return None
        result = self._workflow_engine.get_result(workflow_id)
        return result.to_dict() if result else None
