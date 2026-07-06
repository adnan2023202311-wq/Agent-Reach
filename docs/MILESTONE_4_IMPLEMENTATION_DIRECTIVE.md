# Agent-Reach Milestone 4 Implementation Directive

Version: 1.0

Status: Approved

This document is the authoritative implementation specification for Milestone 4.

If implementation conflicts with this document, this document takes precedence.

---

# Mission

Milestone 4 transforms Agent-Reach from a plugin runtime into an autonomous AI operating system.

The objective is to introduce intelligent orchestration, reusable skills, long-term knowledge, workflow execution, evaluation, reflection, observability, and standardized tool access while preserving the architecture established during Milestones 1–3.

Milestone 4 MUST extend the existing architecture.

It MUST NOT redesign it.

---

# Core Components (Required)

Arena MUST implement the following native subsystems.

1. Workflow Engine

2. Scheduler

3. Execution Engine Improvements

4. Evaluation Engine

5. Reflection Engine

6. Memory Layer

7. Knowledge Layer

8. Skill Engine

9. Capability Resolver

10. MCP Runtime

11. Observability Layer

12. Runtime Metrics

13. Integration Tests

14. Documentation

---

# Mandatory Runtime Architecture

Mission

↓

Planner

↓

Workflow Engine

↓

Scheduler

↓

Execution Engine

↓

Evaluation Engine

↓

Reflection Engine

↓

Memory Layer

↓

Knowledge Layer

↓

Skill Engine

↓

Capability Resolver

↓

MCP Runtime

↓

Tools

Arena MUST preserve this execution order.

---

# Research Inspirations

Before implementing each subsystem, Arena MUST study the architectural concepts of the following projects.

The purpose is inspiration only.

Arena MUST NOT copy implementations.

Arena MUST build native Agent-Reach components.

| Project | Adopt | Reject | Build |
|---------|-------|--------|-------|
| Agent Skills | Skill philosophy, reusable skills | External dependency | Native Skill Engine |
| LongCat | Long-context memory architecture | Copy implementation | Native Memory Layer |
| Mem0 | Memory lifecycle | Library dependency | Native Memory Manager |
| Zep | Knowledge indexing & retrieval | External service coupling | Native Knowledge Layer |
| LangGraph | DAG workflow, checkpoints, state management | Framework lock-in | Native Workflow Engine |
| Claude Code | Incremental engineering workflow | Closed implementation | Native Engineering Loop |
| OpenHands | Workspace execution | Monolithic architecture | Native Workspace Runtime |
| Codex CLI | Git-centric development workflow | CLI dependency | Native Git Integration |
| MCP | Standard tool protocol | Vendor-specific integrations | Native MCP Runtime |
| DeepEval | Evaluation metrics | Library dependency | Native Evaluation Engine |
| LangSmith | Execution tracing | Cloud dependency | Native Observability |
| Phoenix | Runtime diagnostics | External platform | Native Diagnostics |
| PageAgent | Context-aware workspace concepts | UI-specific implementation | Native Workspace Experience |
| Agent Reach (original inspiration) | Architectural ideas only | Copying repository structure or implementation | Native Agent-Reach architecture |

---

# Mandatory Architecture Decisions

ADR-001

Plugins contain Skills.

Plugins are containers.

Business logic belongs inside Skills.

---

ADR-002

Evaluation ALWAYS happens before Reflection.

Reflection consumes evaluation results.

Reflection never replaces evaluation.

---

ADR-003

Memory

Knowledge

Skills

are independent subsystems.

They MUST NOT be merged.

---

ADR-004

Planner never executes.

Execution Engine never plans.

Workflow Engine owns orchestration.

---

ADR-005

Capability Resolver is mandatory.

Planner MUST never call tools directly.

---

ADR-006

Everything important is observable.

Every execution produces metrics.

Every execution produces traces.

---

ADR-007

Arena MUST prefer native implementations over framework dependencies.

---

# Engineering Rules

Arena MUST

• Build interfaces before implementations.

• Implement incrementally.

• Write unit tests.

• Write integration tests.

• Keep commits small.

• Update documentation continuously.

• Preserve compatibility with Milestones 1–3.

• Maintain clean architecture.

• Keep components replaceable.

• Avoid framework lock-in.

Arena MUST NOT

• Redesign existing architecture.

• Copy external project implementations.

• Introduce unnecessary dependencies.

• Skip tests.

• Skip documentation.

• Merge unrelated responsibilities.

---

# Folder Structure

Milestone 4 should extend

backend/

agent-reach-core/

agent_reach/

core/

workflow/

evaluation/

reflection/

memory/

knowledge/

skills/

mcp/

observability/

tests/

without breaking existing architecture.

---

# Testing Requirements

Every subsystem MUST include

Unit Tests

Integration Tests

Architecture Validation

Regression Tests

Performance Validation where applicable.

No subsystem is complete until all tests pass.

---

# Git Workflow

Arena MUST

Implement

↓

Test

↓

Commit

↓

Verify

↓

Update Documentation

↓

Run Full Test Suite

↓

Synchronize GitHub

↓

Continue

Never continue after failing tests.

---

# Definition of Done

Milestone 4 is complete only if

✓ All required subsystems are implemented.

✓ Existing functionality remains operational.

✓ Unit tests pass.

✓ Integration tests pass.

✓ Documentation updated.

✓ Git status clean.

✓ Repository synchronized with GitHub.

✓ Final implementation report generated.

---

# Final Directive

This document is the single source of truth for Milestone 4.

Arena MUST understand the architectural ideas behind the referenced projects.

Arena MUST NOT reproduce those projects.

Arena MUST build native Agent-Reach implementations inspired by the engineering concepts described above.

The final objective is to create a modular, extensible, self-improving AI operating system while preserving the architectural philosophy established during Milestones 1–3.
