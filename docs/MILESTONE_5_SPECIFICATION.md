# Agent-Reach
# Milestone 5 Specification
Version: 1.1

---

# Objective

Milestone 5 introduces the Workflow & Orchestration Layer.

Milestone 5 transforms Agent-Reach from a collection of executable agents into a workflow-driven AI operating system.

No redesign of previous milestones is allowed.

---

# Semantic Definitions (M5 Amendment 1.1)

These definitions were added during M5 implementation to
disambiguate semantics that the original v1.0 spec left open.
Future M5 work MUST follow these definitions; the implementation
must not reinterpret them locally.

## StepExecutionRecord.attempts

`StepExecutionRecord.attempts` records **the number of times
the WorkflowEngine invoked the step**, bounded by the resolved
`RetryPolicy.max_attempts`.

- A step that succeeds on the first engine-level call records
  `attempts=1`.
- A step configured with `max_attempts=2` records `attempts=2`
  whether it ultimately succeeds or fails.
- Inner orchestrator retries (e.g., AgentDispatcher\'s own
  per-call retry policy) are an implementation detail of that
  orchestrator and are NOT reflected in this field.
- Inner orchestrator retry counts are visible via the
  underlying `AgentResult.attempts` / `OrchestrationResult.attempts`
  if a caller needs them; the workflow-level audit only reports
  the engine-level count.

Rationale: this matches what the workflow author configured via
`RetryPolicy.max_attempts` ("retry up to N times → attempts=N")
and avoids multiplicative composition with inner orchestrator
retry policies.

## WorkflowContext.history

`WorkflowContext.history` is the ordered list of
`StepExecutionRecord`s for the current workflow run, one per
step execution attempt sequence (NOT per individual underlying
invocation). The list is append-only.

---

# Scope

Implement the complete Workflow Layer.

Reuse Milestones 1–4.

Do not duplicate existing runtime, planner, memory, execution engine or plugin infrastructure.

---

# Deliverables

## M5.1 Workflow Models

Implement:

- Workflow
- WorkflowStep
- WorkflowContext
- WorkflowState
- WorkflowResult

Support:

- metadata
- variables
- outputs
- execution history

---

## M5.2 Workflow Engine

Implement:

- WorkflowEngine

Responsibilities:

- execute workflows
- execute sequential steps
- branch execution
- merge outputs
- retry failed steps

Support:

- synchronous execution

No distributed execution.

---

## M5.3 Workflow Registry

Implement:

- WorkflowRegistry

Responsibilities:

- register workflows
- load workflows
- retrieve workflows
- unregister workflows

---

## M5.4 Agent Orchestration

Allow workflows to invoke multiple agents.

Support:

- sequential agents
- conditional agents
- shared context

Reuse Runtime Layer.

---

## M5.5 Tool Orchestration

Allow workflow steps to execute tools.

Support:

- tool invocation
- parameter passing
- output propagation

Reuse ToolExecutor.

---

## M5.6 Workflow Persistence

Implement:

- save workflow
- load workflow
- execution history

JSON storage only.

No database.

---

## M5.7 Workflow Validation

Validate:

- cycles
- missing agents
- missing tools
- invalid transitions
- invalid variables

---

## M5.8 Monitoring

Track:

- workflow duration
- workflow failures
- completed workflows
- active workflows
- execution statistics

---

## M5.9 Tests

Create:

Unit tests

Integration tests

Workflow execution tests

Workflow persistence tests

Workflow validation tests

Regression tests

Existing Milestone 1–4 tests must continue passing.

---

## M5.10 Documentation

Update:

README.md

TECHNICAL_DEBT.md

Architecture documentation

Workflow documentation

---

# Engineering Rules

Architecture is frozen.

Reuse previous milestones.

Do not duplicate implementations.

Commit after every subsystem.

Run tests after every subsystem.

Fix implementation bugs immediately.

---

# Dependency Rules

No new dependencies unless absolutely necessary.

If required:

- justify them
- update project configuration
- explain why existing libraries are insufficient

---

# Testing Rules

Treat tests as the specification.

Do not continue while tests fail.

Run the complete test suite before completion.

---

# Technical Debt

Record only.

Do not fix unrelated debt.

---

# Completion Checklist

Milestone 5 is complete only when:

✓ All deliverables implemented

✓ Existing tests pass

✓ New tests pass

✓ Documentation updated

✓ Working tree clean

✓ Local commits created

✓ Commits pushed to GitHub

✓ Completion report written

---

# Out of Scope

Distributed execution

Message brokers

Redis

Kafka

Databases

Authentication

Authorization

REST API expansion

Frontend redesign

Cloud deployment

Sandboxing

LLM provider changes

---

# Stop Condition

After Milestone 5 is complete:

STOP.

Do not begin Milestone 6.
