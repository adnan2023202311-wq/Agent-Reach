# Agent-Reach — Workflows User Guide

This guide shows how to build, register, validate, execute,
persist, and monitor workflows using the M5 Workflow &
Orchestration Layer.

---

# A minimal workflow

```python
from workflows.models import (
    Workflow, WorkflowStep, StepType, WorkflowState,
)
from workflows.engine import WorkflowEngine
from workflows.orchestration import ToolOrchestrator

# 1. Build a tool orchestrator and register a tool.
tools = ToolOrchestrator()

async def add(a: int = 0, b: int = 0) -> int:
    return a + b

tools.executor.register_tool("add", add)

# 2. Build the engine.
engine = WorkflowEngine(tool_orchestrator=tools)

# 3. Define a workflow.
workflow = Workflow(
    name="sum_two",
    variables={"x": 5},
    steps=[
        WorkflowStep(
            step_id="add",
            type=StepType.TOOL,
            target="add",
            inputs={"a": "{{ variables.x }}", "b": 7},
            output_keys=["sum"],
        ),
    ],
    outputs={"total": "outputs.add.sum"},
)

# 4. Run synchronously.
result = engine.run_sync(workflow)
assert result.state == WorkflowState.COMPLETED
assert result.outputs == {"total": 12}
```

---

# Branching on a condition

```python
from workflows.models import Condition, ConditionOp

workflow = Workflow(
    name="branch",
    variables={"go": True},
    steps=[
        WorkflowStep(
            step_id="do_it",
            type=StepType.TOOL,
            target="add",
            inputs={"a": 1, "b": 1},
            condition=Condition("go", ConditionOp.TRUTHY),
            output_keys=["sum"],
        ),
        WorkflowStep(
            step_id="otherwise",
            type=StepType.TOOL,
            target="add",
            inputs={"a": 100, "b": 100},
            condition=Condition(
                "outputs.do_it.sum", ConditionOp.GTE, value=2
            ),
            output_keys=["sum"],
        ),
    ],
    outputs={"final": "outputs.otherwise.sum"},
)
```

When `go` is False, the first step is skipped (recorded as
`skipped=True, success=True`), and the second step's condition
becomes False because `outputs.do_it.sum` was never produced.

---

# Retries

Retry policies are resolved in this order: step → workflow
default → engine default → none. The maximum of attempts that
were actually performed is recorded in
`StepExecutionRecord.attempts`.

```python
from domain.models import RetryPolicy

engine = WorkflowEngine(
    tool_orchestrator=tools,
    default_retry_policy=RetryPolicy(
        max_attempts=3, backoff_seconds=0.0,
    ),
)
```

A failing step runs up to three times; if every attempt fails,
the workflow is marked FAILED and execution stops.

---

# Reusing agents

```python
from core.dispatcher import AgentDispatcher
from domain.models import AgentType, RetryPolicy
from workflows.orchestration import AgentOrchestrator

dispatcher = AgentDispatcher(
    agents={AgentType.RESEARCH: my_research_agent},
    retry_policy=RetryPolicy(max_attempts=2),
)

engine = WorkflowEngine(
    agent_orchestrator=AgentOrchestrator(dispatcher=dispatcher),
    tool_orchestrator=tools,
)
```

Steps of type `AGENT` route through the existing M3 dispatcher
so the retry, timeout, and error-wrapping behavior stays
identical to direct agent calls.

---

# Registry, validation, and persistence

```python
from workflows.registry import WorkflowRegistry
from workflows.validation import WorkflowValidator
from workflows.persistence import save_workflow, load_workflow

reg = WorkflowRegistry()
reg.register(workflow)

# Validate against the live dispatcher / tool manager.
result = WorkflowValidator(
    dispatcher=dispatcher, executor=tools.executor,
).validate(workflow)
assert result.valid, result.errors

# Save and reload.
save_workflow(workflow, "greet.json")
reloaded = load_workflow("greet.json")
```

---

# Monitoring

```python
from workflows.monitoring import WorkflowMonitor

monitor = WorkflowMonitor()
result = engine.run_sync(workflow)
monitor.record(result)

stats = monitor.get_stats()
# stats.total, stats.completed, stats.failed,
# stats.active, stats.average_duration_ms, ...
```

A single monitor object should be shared across the engine and
any code that needs to read stats. The monitor is in-memory
only; cross-process aggregation belongs to a future milestone.

---

# Template expressions

Inputs and workflow-output maps may use one of two equivalent
forms:

- `{{ variables.x }}` — template substitution.
- `variables.x` (bare) — also resolved.

Available namespaces:

- `variables.<name>` — the workflow's variable bag.
- `outputs.<step_id>.<key>` — a previously-produced step output.

The resolver is deliberately narrow: no arithmetic, no loops,
no function calls. Workflow inputs cannot host arbitrary code
execution.

---

# Where to read next

- `docs/MILESTONE_5_SPECIFICATION.md` — the source of truth.
- `docs/MILESTONE_5_ARCHITECTURE.md` — module-by-module
  reference and reuse map.
- `backend/agent reach core/agent_reach/workflows/` — the
  implementation.
- `backend/agent reach core/agent_reach/tests/test_m5_*` — the
  full test suite for M5.
