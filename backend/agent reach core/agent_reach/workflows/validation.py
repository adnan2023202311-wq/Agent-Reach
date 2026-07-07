"""
Workflow & Orchestration Layer — Workflow Validation (M5.7).

Layer: Application/Core — depends inward on domain/ and core/ only.

Static structural validation of :class:`~workflows.models.Workflow`
definitions. Per the M5 specification, a workflow is invalid when:

- it contains a cycle (circular ``depends_on`` chain);
- it references an agent that is not registered in the dispatcher;
- it references a tool that is not registered in the ToolManager;
- it has an invalid transition (e.g. depends on an unknown step);
- it references a variable or output that does not exist.

Validation is purely structural — it does NOT execute the
workflow and does not need an instance of the orchestrator
machinery beyond a lightweight description of what is registered.
Two flavors of check are provided:

- :class:`WorkflowValidator` — registered agents + tools can be
  injected so the validator can also check "missing agents/tools"
  against the live system.
- :func:`validate_structure` — purely structural checks that do
  not require any registry. Always available, even when no
  orchestrator has been built yet.

Both report a :class:`ValidationResult` so callers can see all
problems at once rather than fixing them one by one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from core.dispatcher import AgentDispatcher
from core.tool_executor import ToolExecutor
from workflows.models import Workflow, WorkflowStep


@dataclass
class ValidationResult:
    """Outcome of validating a Workflow.

    Attributes:
        valid: True iff no errors were found. Warnings do not
            affect ``valid``.
        errors: list of human-readable error strings.
        warnings: list of human-readable warning strings.
    """

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: ValidationResult) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.valid:
            self.valid = False


def _detect_cycle(
    steps: list[WorkflowStep],
) -> Optional[list[str]]:
    """Detect a cycle in ``depends_on`` edges via DFS coloring.

    Returns the list of step_ids forming the cycle, or None if no
    cycle is present. Self-loops (step.depends_on contains the
    step itself) are reported as a 1-step cycle.
    """
    step_by_id: dict[str, WorkflowStep] = {s.step_id: s for s in steps}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in step_by_id}

    cycle_path: list[str] = []

    def dfs(node: str, path: list[str]) -> bool:
        color[node] = GRAY
        path.append(node)
        for dep in step_by_id[node].depends_on:
            if dep not in step_by_id:
                continue
            if color[dep] == GRAY:
                # Found a back-edge — extract the cycle from the path.
                idx = path.index(dep)
                cycle_path.extend(path[idx:])
                cycle_path.append(dep)
                return True
            if color[dep] == WHITE and dfs(dep, path):
                return True
        path.pop()
        color[node] = BLACK
        return False

    for sid in step_by_id:
        if color[sid] == WHITE:
            if dfs(sid, []):
                return cycle_path
    return None


def _check_template_refs(
    inputs: object,
    variables: dict[str, object],
    step_outputs_seen: set[str],
) -> list[str]:
    """Return error messages for unresolved template references.

    ``variables`` carries the workflow-level variables bag;
    ``step_outputs_seen`` is the set of step_ids that have already
    produced outputs at this point in the workflow. References to
    outputs of later steps are flagged because they cannot be
    resolved at run time (steps execute in declared order).
    """
    # Local imports avoid a cycle when this module is imported
    # alongside the engine / template modules.
    from workflows.template import _TEMPLATE_RE, _BARE_PATH_RE  # noqa: WPS433

    errors: list[str] = []
    stack: list[object] = [inputs]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
            continue
        if isinstance(item, list):
            stack.extend(item)
            continue
        if not isinstance(item, str):
            continue

        # Bare paths
        if _BARE_PATH_RE.match(item):
            head = item.split(".", 1)[0]
            if head == "variables":
                name = item.split(".", 2)[1]
                if name not in variables:
                    errors.append(f"Reference to undefined variable: {item!r}")
            elif head == "outputs":
                parts = item.split(".")
                if len(parts) >= 3:
                    ref_step = parts[1]
                    if ref_step not in step_outputs_seen:
                        errors.append(
                            f"Reference to output of step that has not run yet: {item!r}"
                        )
            continue

        # {{ path }} expressions
        for match in _TEMPLATE_RE.finditer(item):
            path = match.group(1)
            head = path.split(".", 1)[0]
            if head == "variables":
                name = path.split(".", 2)[1]
                if name not in variables:
                    errors.append(f"Template references undefined variable: {path!r}")
            elif head == "outputs":
                parts = path.split(".")
                if len(parts) >= 3:
                    ref_step = parts[1]
                    if ref_step not in step_outputs_seen:
                        errors.append(
                            f"Template references output of step that has not run yet: {path!r}"
                        )
    return errors


def validate_structure(workflow: Workflow) -> ValidationResult:
    """Pure structural validation — no registry needed.

    Checks:
    - duplicate step_ids
    - empty / malformed name
    - missing ``target`` on every step
    - cycles in ``depends_on``
    - unknown dependency targets
    - template references to undefined variables or to outputs of
      steps that have not yet executed (in declared order)
    - workflow-level ``outputs`` references unknown steps
    """
    result = ValidationResult()

    # Name must be non-empty
    if not workflow.name:
        result.add_error("Workflow.name must be non-empty")

    # Steps must have IDs and targets
    if not workflow.steps:
        result.add_warning("Workflow has no steps")

    seen_ids: set[str] = set()
    for step in workflow.steps:
        if not step.step_id:
            result.add_error(f"WorkflowStep missing step_id (name={step.name!r})")
            continue
        if step.step_id in seen_ids:
            result.add_error(f"Duplicate step_id: {step.step_id!r}")
        seen_ids.add(step.step_id)

        if not step.target:
            result.add_error(
                f"Step {step.step_id!r} has no target (type={step.type.value})"
            )

        for dep in step.depends_on:
            if dep == step.step_id:
                result.add_error(
                    f"Step {step.step_id!r} depends on itself"
                )

    # Cycle detection (DFS over depends_on edges).
    cycle = _detect_cycle(workflow.steps)
    if cycle:
        result.add_error(f"Dependency cycle detected: {' -> '.join(cycle)}")

    # Unknown dependencies.
    for step in workflow.steps:
        for dep in step.depends_on:
            if dep not in seen_ids:
                result.add_error(
                    f"Step {step.step_id!r} depends on unknown step {dep!r}"
                )

    # Template references — variables not defined, outputs of
    # steps that have not yet run.
    variables = workflow.variables
    produced_so_far: set[str] = set()
    produced_outputs: dict[str, set[str]] = {}
    for step in workflow.steps:
        for msg in _check_template_refs(
            step.inputs, variables, produced_so_far
        ):
            result.add_error(f"Step {step.step_id!r}: {msg}")
        if step.condition is not None:
            from workflows.conditions import _resolve_condition_variable  # noqa: WPS433

            try:
                _resolve_condition_variable(step.condition.variable, type("_", (), {
                    "variables": variables,
                    "step_outputs": {},
                })())
            except KeyError:
                # Validate against the actual visible namespace at
                # this point in the declared order.
                from workflows.models import WorkflowContext  # noqa: WPS433

                fake_ctx = WorkflowContext(
                    workflow_id=workflow.workflow_id,
                    variables=variables,
                    step_outputs={
                        sid: {k: None for k in produced_outputs.get(sid, set())}
                        for sid in produced_so_far
                    },
                )
                try:
                    _resolve_condition_variable(step.condition.variable, fake_ctx)
                except KeyError:
                    result.add_error(
                        f"Step {step.step_id!r}: condition references "
                        f"unknown variable or step output: "
                        f"{step.condition.variable!r}"
                    )

        produced_so_far.add(step.step_id)
        # Track declared output_keys so condition validation knows
        # which keys exist on already-produced step outputs.
        if step.output_keys:
            produced_outputs[step.step_id] = set(step.output_keys)
        else:
            produced_outputs[step.step_id] = set()

    # Workflow-level outputs must reference known steps.
    for out_name, path in workflow.outputs.items():
        if not isinstance(path, str) or not path.startswith("outputs."):
            # variables.* references are allowed and checked below.
            if not (isinstance(path, str) and path.startswith("variables.")):
                result.add_error(
                    f"Workflow output {out_name!r} path {path!r} is not a "
                    f"variables.* or outputs.* reference"
                )
                continue
            parts = path.split(".")
            if len(parts) < 2:
                result.add_error(
                    f"Workflow output {out_name!r} has malformed path {path!r}"
                )
                continue
            var_name = parts[1]
            if var_name not in variables:
                result.add_error(
                    f"Workflow output {out_name!r} references undefined variable: {path!r}"
                )
            continue
        parts = path.split(".")
        if len(parts) < 3:
            result.add_error(
                f"Workflow output {out_name!r} has malformed outputs path: {path!r}"
            )
            continue
        ref_step = parts[1]
        if ref_step not in seen_ids:
            result.add_error(
                f"Workflow output {out_name!r} references unknown step: {path!r}"
            )

    return result


class WorkflowValidator:
    """Validates a Workflow against both its structure and a live registry.

    Used when the caller wants to know "is this workflow runnable
    right now?" rather than just "is this workflow well-formed?".

    Parameters
    ----------
    dispatcher:
        AgentDispatcher whose registered_agent_types() is used to
        detect "missing agent" errors. Pass None to skip agent
        registration checks.
    executor:
        ToolExecutor whose tool_manager.registered names are used
        to detect "missing tool" errors. Pass None to skip tool
        registration checks.
    """

    def __init__(
        self,
        dispatcher: Optional[AgentDispatcher] = None,
        executor: Optional[ToolExecutor] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._executor = executor

    def validate(self, workflow: Workflow) -> ValidationResult:
        """Run structural + registry-aware validation."""
        result = validate_structure(workflow)

        if self._dispatcher is not None:
            registered_agents = {
                t.value for t in self._dispatcher.registered_agent_types()
            }
            for step in workflow.steps:
                if step.type.value != "agent":
                    continue
                if step.target not in registered_agents:
                    result.add_error(
                        f"Step {step.step_id!r} targets unregistered agent: "
                        f"{step.target!r}"
                    )

        if self._executor is not None:
            registered_tools = set(
                self._executor.tool_manager._tools.keys()  # noqa: WPS437
            )
            for step in workflow.steps:
                if step.type.value != "tool":
                    continue
                if step.target not in registered_tools:
                    result.add_error(
                        f"Step {step.step_id!r} targets unregistered tool: "
                        f"{step.target!r}"
                    )

        return result


def validate_many(
    workflows: Iterable[Workflow],
    validator: Optional[WorkflowValidator] = None,
) -> dict[str, ValidationResult]:
    """Validate a collection of workflows.

    Returns a map of workflow.name -> ValidationResult. Using the
    name as the key (rather than workflow_id) makes the result
    friendlier for human inspection.
    """
    out: dict[str, ValidationResult] = {}
    for wf in workflows:
        result = (
            validator.validate(wf)
            if validator is not None
            else validate_structure(wf)
        )
        out[wf.name] = result
    return out


__all__ = [
    "ValidationResult",
    "WorkflowValidator",
    "validate_many",
    "validate_structure",
]
