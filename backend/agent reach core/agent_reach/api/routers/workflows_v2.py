"""
API layer: /api/v1/workflows/v2 — Visual Workflow Builder V2 (M10.6).

Extends the existing M5 workflow engine with visual builder features:
loops, conditions, parallel branches, human approval gates, scheduling,
events, and error handling.

This router builds on the existing WorkflowEngine (does NOT replace it).
V2 workflows are defined as node graphs with typed edges; the engine
compiles them into the existing TaskPlan/SubTask model for execution.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workflows/v2", tags=["visual-workflow-v2"])


# ── Node type enum ──────────────────────────────────────────────────────

class NodeType:
    AGENT = "agent"
    TOOL = "tool"
    CONDITION = "condition"
    LOOP = "loop"
    PARALLEL = "parallel"
    HUMAN_APPROVAL = "human_approval"
    SCHEDULE = "schedule"
    EVENT = "event"
    ERROR_HANDLER = "error_handler"


# ── Schemas ─────────────────────────────────────────────────────────────

class WorkflowNode(BaseModel):
    node_id: str
    node_type: str
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=dict)  # x, y for visual layout


class WorkflowEdge(BaseModel):
    edge_id: str = ""
    source: str  # node_id
    target: str  # node_id
    label: str = ""  # e.g. "true" / "false" for condition branches
    condition: Optional[str] = None  # expression for conditional edges


class V2Workflow(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    schedule: Optional[str] = None  # cron expression
    enabled: bool = True


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    schedule: Optional[str] = None


# ── In-memory store (swap for DB in production) ────────────────────────

_workflows: dict[str, V2Workflow] = {}
_approval_requests: dict[str, dict[str, Any]] = {}


# ── Endpoints ───────────────────────────────────────────────────────────

@router.post("")
async def create_workflow(request: CreateWorkflowRequest) -> dict[str, Any]:
    """Create a new visual workflow."""
    wf = V2Workflow(
        name=request.name,
        description=request.description,
        nodes=request.nodes,
        edges=request.edges,
        schedule=request.schedule,
    )
    _workflows[wf.workflow_id] = wf
    return {
        "workflow_id": wf.workflow_id,
        "name": wf.name,
        "node_count": len(wf.nodes),
        "edge_count": len(wf.edges),
        "status": "created",
    }


@router.get("")
async def list_workflows() -> dict[str, Any]:
    """List all V2 workflows."""
    return {
        "workflows": [
            {
                "workflow_id": wf.workflow_id,
                "name": wf.name,
                "description": wf.description,
                "node_count": len(wf.nodes),
                "enabled": wf.enabled,
                "schedule": wf.schedule,
            }
            for wf in _workflows.values()
        ],
        "count": len(_workflows),
    }


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    """Get a V2 workflow with full node/edge graph."""
    wf = _workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.model_dump()


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, request: CreateWorkflowRequest) -> dict[str, Any]:
    """Update a V2 workflow's graph."""
    wf = _workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.name = request.name
    wf.description = request.description
    wf.nodes = request.nodes
    wf.edges = request.edges
    wf.schedule = request.schedule
    return {"status": "updated", "workflow_id": workflow_id}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str) -> dict[str, Any]:
    """Delete a V2 workflow."""
    if _workflows.pop(workflow_id, None) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted", "workflow_id": workflow_id}


class ExecuteWorkflowRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: ExecuteWorkflowRequest,
    pipeline: Any = None,
) -> dict[str, Any]:
    """Execute a V2 workflow.

    Walks the node graph in topological order. For each node:
    - AGENT: dispatches through the pipeline's controller
    - TOOL: calls the tool runtime (if available)
    - CONDITION: evaluates the condition expression and follows the
      matching edge
    - LOOP: iterates over a list, executing the loop body for each item
    - PARALLEL: executes all outgoing edges concurrently
    - HUMAN_APPROVAL: pauses and creates an approval request
    - ERROR_HANDLER: catches errors from the source node and runs
      recovery logic

    For now, this is a simplified executor that handles AGENT nodes
    and passes through the rest as no-ops with metadata. Full execution
    semantics will be layered in subsequent batches.
    """
    wf = _workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    results: list[dict[str, Any]] = []
    for node in wf.nodes:
        if node.node_type == NodeType.AGENT:
            query = node.config.get("query", node.label)
            if pipeline:
                try:
                    outcome = await pipeline._controller.handle_request(query)
                    results.append({
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "status": outcome.status.value,
                        "answer": outcome.answer[:500],
                    })
                except Exception as exc:
                    results.append({
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "status": "failed",
                        "error": str(exc)[:200],
                    })
            else:
                results.append({
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "status": "skipped",
                    "reason": "pipeline not available",
                })
        elif node.node_type == NodeType.HUMAN_APPROVAL:
            approval_id = str(uuid.uuid4())
            _approval_requests[approval_id] = {
                "workflow_id": workflow_id,
                "node_id": node.node_id,
                "prompt": node.config.get("prompt", "Approval required"),
                "status": "pending",
            }
            results.append({
                "node_id": node.node_id,
                "node_type": node.node_type,
                "status": "pending_approval",
                "approval_id": approval_id,
            })
        else:
            results.append({
                "node_id": node.node_id,
                "node_type": node.node_type,
                "status": "skipped",
                "reason": f"{node.node_type} nodes are metadata-only in this batch",
            })

    return {
        "workflow_id": workflow_id,
        "executed_nodes": len(results),
        "results": results,
        "status": "completed",
    }


# ── Human approval endpoints ───────────────────────────────────────────

class ApprovalDecisionRequest(BaseModel):
    approved: bool
    comment: str = ""


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str) -> dict[str, Any]:
    """Get an approval request's status."""
    req = _approval_requests.get(approval_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return req


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
) -> dict[str, Any]:
    """Approve or reject a human-approval gate."""
    req = _approval_requests.get(approval_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    req["status"] = "approved" if request.approved else "rejected"
    req["comment"] = request.comment
    req["decided_at"] = __import__("time").time()
    return {"status": req["status"], "approval_id": approval_id}


# ── Node type catalog (for the visual builder UI) ───────────────────────

@router.get("/node-types/catalog")
async def node_type_catalog() -> dict[str, Any]:
    """Return the catalog of available node types for the visual builder."""
    return {
        "node_types": [
            {
                "type": NodeType.AGENT,
                "label": "Agent",
                "description": "Dispatch a subtask to an agent",
                "config_fields": ["query", "agent_type"],
                "inputs": 1,
                "outputs": 1,
            },
            {
                "type": NodeType.TOOL,
                "label": "Tool",
                "description": "Execute a tool",
                "config_fields": ["tool_name", "args"],
                "inputs": 1,
                "outputs": 1,
            },
            {
                "type": NodeType.CONDITION,
                "label": "Condition",
                "description": "Branch based on a condition expression",
                "config_fields": ["expression"],
                "inputs": 1,
                "outputs": 2,
                "output_labels": ["true", "false"],
            },
            {
                "type": NodeType.LOOP,
                "label": "Loop",
                "description": "Iterate over a list",
                "config_fields": ["items", "variable_name"],
                "inputs": 1,
                "outputs": 1,
            },
            {
                "type": NodeType.PARALLEL,
                "label": "Parallel",
                "description": "Execute all outgoing branches concurrently",
                "config_fields": [],
                "inputs": 1,
                "outputs": -1,
            },
            {
                "type": NodeType.HUMAN_APPROVAL,
                "label": "Human Approval",
                "description": "Pause and wait for a human to approve",
                "config_fields": ["prompt", "timeout_seconds"],
                "inputs": 1,
                "outputs": 2,
                "output_labels": ["approved", "rejected"],
            },
            {
                "type": NodeType.SCHEDULE,
                "label": "Schedule",
                "description": "Trigger the workflow on a cron schedule",
                "config_fields": ["cron_expression"],
                "inputs": 0,
                "outputs": 1,
            },
            {
                "type": NodeType.EVENT,
                "label": "Event",
                "description": "Trigger on an external event",
                "config_fields": ["event_type"],
                "inputs": 0,
                "outputs": 1,
            },
            {
                "type": NodeType.ERROR_HANDLER,
                "label": "Error Handler",
                "description": "Catch errors from a source node",
                "config_fields": ["recovery_strategy"],
                "inputs": 1,
                "outputs": 1,
            },
        ]
    }
