# Agent Reach

An extensible AI Operating System designed to orchestrate AI agents, tools,
providers, memory systems, workflows, and future capabilities through a modular
plugin architecture.

## Repository Structure

```
backend/agent-reach-core/       Plugin system foundation (Milestone 1) +
                                Execution Engine (Milestone 2)
backend/agent reach core/       Kernel, API, agents, and Agent Runtime
                                (Milestone 3)
frontend/Agent Canvas/          Production frontend (TanStack Start)
docs/                           Project documentation
```

## Milestones

### Milestone 1 — Plugin Foundation (Complete)
- Capability Registry with dependency validation
- Plugin Manifest and JSON Schemas
- Plugin Loader interfaces + Static Plugin Loader
- Contract Registry and Validator
- Schema Resolution
- Comprehensive tests

### Milestone 2 — Execution Engine & Kernel Bridge (Complete)
- Dynamic Plugin Loader (filesystem discovery)
- Plugin Manager (lifecycle orchestration)
- Execution Engine (input/output contract validation)
- Event Bus (inter-plugin communication)
- Configuration Validator
- Kernel Bridge (integrates plugin system with existing kernel)
- Comprehensive tests

### Milestone 3 — Agent Runtime Layer (Complete)
- Agent Runtime (session lifecycle, state transitions, cancellation)
- Agent Base (abstract class with initialize/execute/shutdown hooks)
- Planner (Plan, PlanStep, sequential and conditional branch support)
- Tool Executor (timeout handling, exception isolation, metrics)
- Memory Bridge (read/write memory, conversation and execution history)
- Agent Communication (in-process messaging, delegation, events)
- Runtime Monitoring (execution metrics, statistics, agent status)
- Comprehensive tests

### Milestone 4 — Autonomous AI Operating System (Complete)
- Observability Layer (in-process execution tracing with spans and traces)
- Runtime Metrics (counters, gauges, histograms with aggregation)
- Capability Resolver (maps capability IDs to executors with fallback chains)
- MCP Runtime (native Model Context Protocol tool registry and execution)
- Skill Engine (reusable business logic units with registry and batch execution)
- Knowledge Layer (in-memory knowledge indexing, search, and retrieval)
- Memory Layer (long-context memory with lifecycle: short_term → long_term → archived)
- Evaluation Engine (criteria-based scoring with weighted aggregation)
- Reflection Engine (insight generation from evaluation results)
- Execution Engine Improvements (orchestrator with parallel execution and tracing)
- Scheduler (priority queue with delayed execution and cancellation)
- Workflow Engine (DAG orchestration with checkpoints, evaluation, and reflection)
- Integration Tests (end-to-end pipeline verification)
- Documentation updated

### Milestone 5 — Workflow & Orchestration Layer (Complete)
- **Workflow Models**: Workflow, WorkflowStep, WorkflowContext,
  WorkflowState, WorkflowResult, Condition (structured
  conditional with JSON round-trip), StepExecutionRecord.
- **WorkflowEngine**: runs workflows synchronously (run_sync) or
  asynchronously (run); executes steps in declared order;
  honors `condition` to skip branches and `depends_on` to skip
  dependents when a dependency was skipped/failed; resolves
  `{{ variables.x }}` and `{{ outputs.step_id.key }}` templates
  in inputs and workflow outputs; retries failed steps per the
  resolved `RetryPolicy` (step → workflow → engine default →
  none).
- **WorkflowRegistry**: in-memory lookup table for named
  workflows; per-name version counter; bulk-load helper.
- **AgentOrchestration**: workflows invoke M3 agents through
  `AgentDispatcher` (sequential, conditional, shared context).
- **ToolOrchestration**: workflows invoke M3 tools through
  `ToolExecutor` with parameter passing and output propagation.
- **WorkflowPersistence**: JSON-only save/load for single
  workflows, lists of workflows, single results, and lists of
  results. Atomic writes (sibling `.tmp` + `os.replace`).
- **WorkflowValidator**: structural checks (cycles, missing
  targets, undefined variables, forward step-output references,
  malformed workflow outputs, unknown conditions) plus optional
  registry-aware checks for unregistered agents/tools.
- **WorkflowMonitor**: in-process stats — total, completed,
  failed, cancelled, active, duration distribution, per-workflow
  run count.
- **Integration Tests**: 10 tests exercising Registry, Engine,
  Persistence, Validation, and Monitoring together.
- **Documentation**: this README + a dedicated M5 doc.

The M5 layer lives in
`backend/agent reach core/agent_reach/workflows/` and is distinct
from M4\'s capability-driven DAG WorkflowEngine in
`backend/agent reach core/agent_reach/workflow/` — both remain
in use and can coexist.

## Running Tests

```bash
# Plugin system tests
cd backend/agent-reach-core
pytest tests/

# Kernel + Runtime + M4 + M5 tests
cd "backend/agent reach core"
pytest agent_reach/tests/ \
  --ignore=agent_reach/tests/test_composition.py \
  --ignore=agent_reach/tests/test_model_client.py
```

## Architecture Principles

- **Plugin First**: Every capability becomes a plugin
- **Kernel Owns Orchestration**: The kernel coordinates, plugins execute
- **Frontend is Presentation Only**: No business logic in the UI
- **Frozen Architecture**: No redesign without explicit approval
- **Composition over Inheritance**: Small, focused classes

See `docs/PROJECT_CHARTER.md` for the full architectural specification.
