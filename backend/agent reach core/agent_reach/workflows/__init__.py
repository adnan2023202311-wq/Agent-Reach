"""Workflow & Orchestration Layer (Milestone 5).

This package introduces the higher-level Workflow & Orchestration
Layer — distinct from the lower-level capability-driven DAG
WorkflowEngine in workflow/engine.py (Milestone 4), which remains
untouched and reusable.

The M5 layer focuses on NAMED workflows that orchestrate agents and
tools, with first-class support for:

- Reusable workflow definitions (metadata, variables, outputs)
- Sequential step execution with branching on conditions
- Per-step retry policies
- JSON persistence of workflow definitions and execution history
- Structural validation (cycles, missing agents/tools, references)
- In-process monitoring of run statistics
- Reuse of existing M1–M4 components (AgentDispatcher, AgentRuntime,
  ToolExecutor, domain.models.RetryPolicy, domain.models.AgentType)

Modules in this package:

- ``models``:      Workflow, WorkflowStep, WorkflowContext,
                   WorkflowState, WorkflowResult, Condition, ...
- ``engine``:      WorkflowEngine — executes workflows
- ``registry``:    WorkflowRegistry — register/load/retrieve workflows
- ``persistence``: JSON save/load for workflows and results
- ``validation``:  WorkflowValidator — static structural validation
- ``monitoring``:  WorkflowMonitor — runtime statistics
- ``conditions``:  Condition evaluator (==, !=, >, <, truthy, ...)
- ``template``:    Template resolver for inputs and outputs
- ``orchestration``: Agent and tool orchestration adapters
"""

from workflows.models import (
    Condition,
    ConditionOp,
    StepExecutionRecord,
    StepType,
    Workflow,
    WorkflowContext,
    WorkflowResult,
    WorkflowState,
    WorkflowStep,
)

__all__ = [
    "Condition",
    "ConditionOp",
    "StepExecutionRecord",
    "StepType",
    "Workflow",
    "WorkflowContext",
    "WorkflowResult",
    "WorkflowState",
    "WorkflowStep",
]
