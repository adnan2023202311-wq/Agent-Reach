# Agent-Reach — Milestone 5 Architecture

Version: 1.0

Companion document to `docs/MILESTONE_5_SPECIFICATION.md`.
Describes how the M5 Workflow & Orchestration Layer fits with
the existing M1–M4 architecture and how its pieces compose.

---

# Purpose

Milestone 5 transforms Agent-Reach from "a collection of
executable agents" into a workflow-driven AI operating system.

The M5 layer focuses on **named, reusable workflows** that
orchestrate agents and tools with first-class support for:

- metadata, variables, and named outputs;
- conditional branches;
- per-step retry policies;
- structural validation;
- JSON persistence;
- execution statistics.

It does NOT replace M4's capability-driven DAG WorkflowEngine —
that engine remains in `workflow/engine.py` and continues to be
the right choice for capability-orchestrated DAGs with
evaluation and reflection integration.

---

# Layering

```
            ┌────────────────────────────────┐
            │  workflows/  (M5)              │
            │  ──────────────────────         │
            │  engine       (WorkflowEngine) │
            │  registry     (WorkflowRegistry)│
            │  persistence  (JSON I/O)        │
            │  validation   (WorkflowValidator)│
            │  monitoring   (WorkflowMonitor)│
            │  orchestration (Agent + Tool)   │
            └────────────────────────────────┘
                       │
                       ▼   reuses
   ┌───────────────────────────────────────────────┐
   │  M3–M4 components (unchanged)                 │
   │  ─────────────────────────                    │
   │  core/dispatcher.py    AgentDispatcher        │
   │  core/tool_executor.py ToolExecutor           │
   │  domain/models.py      RetryPolicy, AgentType │
   │  core/runtime.py       AgentRuntime           │
   │  workflow/engine.py    M4 DAG WorkflowEngine  │
   └───────────────────────────────────────────────┘
```

Every M5 subsystem depends *inward* on M3–M4 components; nothing
in M3–M4 was changed by M5.

---

# Modules

## `workflows/models.py`

Pure data classes — no I/O, no execution.

- `StepType` (AGENT | TOOL)
- `WorkflowState` (PENDING | RUNNING | COMPLETED | FAILED | CANCELLED)
- `ConditionOp` (==, !=, >, <, >=, <=, in, not_in, truthy, falsy)
- `Condition` — `(variable, op, value)` triple with JSON round-trip.
- `WorkflowStep` — id, type, target, inputs, condition,
  depends_on, retry_policy, output_keys, timeout.
- `Workflow` — id, name, description, metadata, variables,
  steps, outputs (name → path), default_retry_policy, version,
  created_at.
- `WorkflowContext` — workflow_id, variables, step_outputs,
  metadata, history.
- `StepExecutionRecord` — per-step audit record.
- `WorkflowResult` — final outcome.

Every model exposes `to_dict()` / `from_dict()` for the M5.6
persistence layer.

## `workflows/template.py`

Dependency-free resolver for `{{ variables.x }}` and
`{{ outputs.step_id.key }}` template expressions. Also resolves
bare paths (no braces) so workflow output maps can be plain
strings.

Why custom:
- Spec forbids new dependencies without justification.
- Intentionally narrow grammar — workflow inputs cannot host
  arbitrary Python evaluation.

## `workflows/conditions.py`

Structured condition evaluator. Compares a context-resolved
value against an expected value using one of the `ConditionOp`
operators. Supports both `variables.x` and bare-name lookups for
ergonomics.

## `workflows/orchestration.py`

Two thin adapters that wrap M3 components so the engine does not
need to know whether a step is an agent or a tool call.

- `AgentOrchestrator` — wraps `AgentDispatcher`, returning a
  uniform `OrchestrationResult`.
- `ToolOrchestrator` — wraps `ToolExecutor`.
- `merge_outputs()` — deterministic merge for branch output
  concatenation (later list values get appended; scalars
  override).

## `workflows/engine.py`

`WorkflowEngine` — the orchestrator.

- `run(workflow, initial_variables=None)` — async.
- `run_sync(workflow, initial_variables=None)` — synchronous,
  blocking, uses `asyncio.run()`.
- Sequential step execution in declared order.
- Honors `condition` (skips a step when False).
- Honors `depends_on` (a skipped/failed dependency also skips
  the dependent).
- Retries failed steps per resolved `RetryPolicy`
  (step → workflow → engine default → none).
- Resolves templates in inputs and workflow outputs.
- Records every attempt in `WorkflowContext.history`.
- Emits a `WorkflowResult` with state, outputs, and history.

`StepExecutionRecord.attempts` is the total number of underlying
agent invocations across engine-level retries — the audit number
a workflow author actually wants to see.

## `workflows/registry.py`

`WorkflowRegistry` — in-memory lookup table.

- `register(workflow)` returns the per-name version (1-based,
  monotonic across unregister/re-register).
- `unregister(name)` returns True/False.
- Lookups by name and by `workflow_id` are O(1).
- `load_from(workflows)` is the bulk-load helper used by the
  persistence layer.

Registry does NOT execute workflows — that responsibility
belongs to the engine. The separation keeps the registry
trivially serializable and easy to replicate later.

## `workflows/persistence.py`

JSON-only I/O for Workflows and WorkflowResults.

- `save_workflow / load_workflow` — single Workflow or list;
  shape auto-detected on load.
- `save_result / load_result` — single WorkflowResult.
- `save_results / load_results` — list of WorkflowResults.
- Atomic writes: write to a sibling `.tmp`, then `os.replace`.
  A test injects a `json.dump` failure to verify the target
  file is never partially written and no `.tmp` litter remains.

## `workflows/validation.py`

Two flavors:

- `validate_structure(workflow)` — pure structural checks:
  duplicate step_ids, missing targets, cycles, unknown
  dependencies, forward step-output references, malformed
  workflow outputs, undefined variables, undefined conditions.
- `WorkflowValidator(dispatcher, executor)` — adds
  registry-aware checks on top:
  "is the targeted agent actually registered?" / "is the
  targeted tool actually registered?".

Both return a `ValidationResult` with `errors` and `warnings`
so callers see every problem in one pass.

## `workflows/monitoring.py`

`WorkflowMonitor` — in-process stats.

- `record(result)` — engine pushes one WorkflowResult per run.
- `mark_active(id)` / `mark_done(id)` — track in-flight workflows.
- `get_stats()` returns a `WorkflowStats` snapshot:
  total / completed / failed / cancelled / active, duration
  distribution (avg / median / min / max), per-workflow run count.
- `get_failures()`, `get_completed()`, `get_results(state=, id=)`
  for filtered queries.

No persistence; cross-process aggregation belongs to a future
milestone.

---

# Workflow Execution Lifecycle

```
1. Workflow is registered with WorkflowRegistry.
2. WorkflowValidator.validate(workflow) gates the run.
3. WorkflowEngine.run(workflow) begins.
4. Engine marks the workflow active on WorkflowMonitor (optional).
5. For each step (in declared order):
   a. Skip if any dependency was skipped or failed.
   b. Skip if condition is False.
   c. Resolve templates in inputs.
   d. Retry per resolved RetryPolicy.
   e. Append a StepExecutionRecord to context.history.
   f. If declared, propagate output_keys into step_outputs.
6. Resolve workflow-level outputs against the final context.
7. WorkflowResult is emitted to WorkflowMonitor.record().
```

---

# Persistence Format

Single workflow (or list) is a JSON object (or array) on disk.
Every model has `to_dict()` / `from_dict()` that produce /
consume JSON-friendly structures.

Example single-workflow file:

```json
{
  "workflow_id": "…",
  "name": "greet",
  "description": "a workflow for testing",
  "metadata": {"owner": "tester"},
  "variables": {"who": "world"},
  "steps": [
    {
      "step_id": "g",
      "name": "greet_step",
      "type": "tool",
      "target": "shout",
      "inputs": {"text": "hello {{ variables.who }}"},
      "condition": null,
      "depends_on": [],
      "retry_policy": null,
      "output_keys": ["text"],
      "timeout_seconds": 30.0
    }
  ],
  "outputs": {"greeting": "outputs.g.text"},
  "default_retry_policy": null,
  "version": "1.0",
  "created_at": 1700000000.0
}
```

Execution results follow the same shape and include a `history`
array of `StepExecutionRecord`s.

---

# Reuse Map (M1–M4 → M5)

| M5 component           | Reuses                                          |
|------------------------|-------------------------------------------------|
| `WorkflowEngine`       | `AgentDispatcher`, `ToolExecutor`, `RetryPolicy`|
| `AgentOrchestrator`    | `AgentDispatcher.dispatch()`                    |
| `ToolOrchestrator`     | `ToolExecutor.execute()`                        |
| `Workflow.to_dict`     | domain enums (`AgentType`, `RetryPolicy`)       |
| `WorkflowValidator`    | `AgentDispatcher.registered_agent_types()`      |
| `WorkflowMonitor`      | (none — pure aggregator)                        |

No M1–M4 component was modified for M5.

---

# What M5 does NOT do

- No distributed execution.
- No message brokers, Redis, Kafka.
- No database — JSON only.
- No authentication / authorization.
- No LLM-driven planning — workflows are author-defined.
- No cross-workflow transactions / rollback.

All of the above are explicitly out of scope per
`docs/MILESTONE_5_SPECIFICATION.md` and belong to future
milestones.
