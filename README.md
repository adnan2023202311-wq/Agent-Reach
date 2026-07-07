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

### Milestone 6 — Production Platform (Complete)

Milestone 6 transforms Agent-Reach from an AI engine into a production-ready
AI platform. It adds usability, production readiness, extensibility, and
developer experience.

- **M6.1 Conversation Engine**: Multi-turn conversations with history,
  memory, and context. Sliding-window memory for context carry-forward.
  Session validation (active state required). `ConversationTurnResult`
  with outcome and metadata.
- **M6.2 Session Manager**: Session lifecycle management (create, resume,
  pause, terminate, delete). Pluggable `SessionStore` protocol with
  `InMemorySessionStore` default. JSON serialization. Session isolation
  by session_id.
- **M6.3 Provider Manager 2.0**: Multi-provider routing with runtime
  switching. Supports Anthropic, OpenAI, Gemini, OpenRouter, DeepSeek,
  Ollama. `ProviderManager` implements `ModelClient` (drop-in replacement).
  Lazy client creation (SDKs imported on first use). Shared
  OpenAI-compatible client for OpenAI/Gemini/OpenRouter/DeepSeek/Ollama.
- **M6.4 Tool Registry 2.0**: Extended tool registry with metadata
  (name, version, description, category, tags), enable/disable, discovery
  (list by category/tag, search), call counting, and stats. Wraps existing
  `ToolManager` (reuses permission/audit logic).
- **M6.5 Agent Registry 2.0**: Dynamic agent registration with metadata,
  dependency validation (category-prefixed dependencies like
  `tools:git_clone`), enable/disable, versioning, and stats.
  `get_enabled_agents()` for `AgentDispatcher` wiring.
- **M6.6 Prompt Library**: Versioned prompt templates with `{{ variable }}`
  substitution. Monotonic versioning per name. Evaluation metadata
  (expected output, criteria, threshold). Discovery and search.
- **M6.7 Developer Playground**: Inspection tool for planners, runtime,
  sessions, memory, and execution history. Workflow execution with full
  result inspection.
- **M6.8 Visual Workflow API**: Backend API for future visual workflow
  editing. `WorkflowNode`, `WorkflowEdge`, `WorkflowGraph` models.
  `to_graph()` / `from_graph()` conversion. Serialization and validation.
- **M6.9 Plugin Marketplace Foundation**: Local plugin marketplace with
  metadata, install/uninstall lifecycle, compatibility validation
  (min_platform_version), version management, and discovery.
- **M6.10 Production API**: Extended FastAPI with conversation endpoints
  (`/api/v1/conversations/sessions`) and workflow endpoints
  (`/api/v1/workflows`). Session CRUD, message sending, history,
  workflow execution, and run results.
- **M6.11 Authentication**: API Key authentication (SHA-256 hashed),
  JWT tokens (HS256 with expiration, python-jose), role-based
  authorization (admin > user > service hierarchy), bcrypt password
  hashing, in-memory `UserStore`.
- **M6.12 Configuration Management**: `ConfigurationManager` with
  environment profiles (development/staging/production), runtime
  overrides, reload from environment, validation, and serialization
  with API key masking.
- **M6.13 Benchmark Suite**: `BenchmarkResult` with timing and memory
  stats. `run_benchmark()` with multi-iteration timing, warmup, and
  optional memory measurement (tracemalloc).
- **M6.14 Official Python SDK**: `AgentReach` class with in-process
  and remote modes. Simple `run()` API. Session management. Context
  manager support. Remote mode via httpx with API key auth.
- **M6.15 Documentation**: This README + updated TECHNICAL_DEBT.md.

## Quick Start

### Python SDK

```python
from agent_reach import AgentReach

app = AgentReach()
result = app.run("Research the best OCR libraries in Python.")
print(result.answer)
```

### REST API

```bash
# Start the server
cd "backend/agent reach core/agent_reach"
uvicorn api.main:app --reload

# Create a session
curl -X POST http://localhost:8000/api/v1/conversations/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-1"}'

# Send a message
curl -X POST http://localhost:8000/api/v1/conversations/sessions/{session_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "message": "Hello, world!"}'
```

## Running Tests

```bash
# Plugin system tests
cd backend/agent-reach-core
pytest tests/

# Kernel + Runtime + M4 + M5 + M6 tests
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
