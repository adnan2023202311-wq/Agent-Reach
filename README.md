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

## Running Tests

```bash
# Plugin system tests
cd backend/agent-reach-core
pytest tests/

# Kernel + Runtime tests
cd "backend/agent reach core/agent_reach"
pytest tests/
```

## Architecture Principles

- **Plugin First**: Every capability becomes a plugin
- **Kernel Owns Orchestration**: The kernel coordinates, plugins execute
- **Frontend is Presentation Only**: No business logic in the UI
- **Frozen Architecture**: No redesign without explicit approval
- **Composition over Inheritance**: Small, focused classes

See `docs/PROJECT_CHARTER.md` for the full architectural specification.
