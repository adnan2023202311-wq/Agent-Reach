"""
Workflow & Orchestration Layer — Condition evaluation (M5.2 helper).

Layer: Application/Core — depends inward on domain/ only.

Evaluate a structured :class:`~workflows.models.Condition` against a
:py:class:`~workflows.models.WorkflowContext`.

Conditions are designed to be:
- Expressible in JSON (so workflows can be persisted and loaded).
- Side-effect-free (no eval/exec of arbitrary Python).
- Easy to test (one operator per case).
"""

from __future__ import annotations

from typing import Any

from workflows.models import Condition, ConditionOp, WorkflowContext


def evaluate_condition(condition: Condition, context: WorkflowContext) -> bool:
    """Return True iff ``condition`` holds against ``context``.

    Resolution rules for ``condition.variable``:
    - A dotted path (``variables.x`` / ``outputs.step_id.key``)
      is resolved against the context; a missing path is a False.
    - A bare name (``x``) is treated as ``variables.x`` for
      convenience.

    Operators:
    - ``EQ``/``NE``: equality comparison (== / !=).
    - ``GT``/``LT``/``GTE``/``LTE``: numeric comparison.
    - ``IN``/``NOT_IN``: membership in a container.
    - ``TRUTHY``/``FALSY``: truthiness (value ignored).
    """
    try:
        actual = _resolve_condition_variable(condition.variable, context)
    except KeyError:
        actual = None

    op = condition.op
    expected = condition.value

    if op is ConditionOp.TRUTHY:
        return bool(actual)
    if op is ConditionOp.FALSY:
        return not bool(actual)
    if op is ConditionOp.EQ:
        return actual == expected
    if op is ConditionOp.NE:
        return actual != expected
    if op is ConditionOp.GT:
        return _safe_compare(actual, expected) is not None and _safe_compare(actual, expected) > 0  # type: ignore[operator]
    if op is ConditionOp.LT:
        cmp = _safe_compare(actual, expected)
        return cmp is not None and cmp < 0  # type: ignore[operator]
    if op is ConditionOp.GTE:
        cmp = _safe_compare(actual, expected)
        return cmp is not None and cmp >= 0  # type: ignore[operator]
    if op is ConditionOp.LTE:
        cmp = _safe_compare(actual, expected)
        return cmp is not None and cmp <= 0  # type: ignore[operator]
    if op is ConditionOp.IN:
        if expected is None:
            return False
        try:
            return actual in expected
        except TypeError:
            return False
    if op is ConditionOp.NOT_IN:
        if expected is None:
            return True
        try:
            return actual not in expected
        except TypeError:
            return True

    # Unknown op — defensively treat as False rather than crashing.
    return False


def _resolve_condition_variable(variable: str, context: WorkflowContext) -> Any:
    """Resolve a Condition variable against a WorkflowContext.

    Accepts both ``variables.x`` and bare ``x`` (treated as a
    variable lookup). Raises ``KeyError`` on miss.
    """
    if variable.startswith("variables.") or variable.startswith("outputs."):
        parts = variable.split(".")
        head = parts[0]
        if head == "variables":
            name = parts[1]
            if name not in context.variables:
                raise KeyError(name)
            return context.variables[name]
        if head == "outputs":
            step_id = parts[1]
            key = parts[2]
            step_out = context.step_outputs.get(step_id, {})
            if key not in step_out:
                raise KeyError(f"{step_id}.{key}")
            return step_out[key]
        raise KeyError(variable)

    # Bare name — treat as a variable lookup.
    if variable in context.variables:
        return context.variables[variable]
    raise KeyError(variable)


def _safe_compare(a: Any, b: Any) -> int:
    """Compare two values, returning ``-1``/``0``/``1`` or ``None``.

    Returns ``None`` if the values cannot be ordered (different
    types, etc.) so callers can choose to skip the comparison rather
    than crash on heterogeneous data.
    """
    try:
        if a < b:
            return -1
        if a > b:
            return 1
        return 0
    except TypeError:
        return None
