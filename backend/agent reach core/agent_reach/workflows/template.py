"""
Workflow & Orchestration Layer — Template resolution (M5.2 helper).

Layer: Application/Core — depends inward on domain/ only.

Tiny, deliberately limited template resolver for Workflow inputs
and outputs. Inputs may contain ``{{ variables.x }}`` or
``{{ outputs.step_id.key }}`` expressions; this module replaces
them with the corresponding value from a WorkflowContext.

A bare path (``outputs.s1.text`` or ``variables.x``, no braces)
is also resolved — this lets ``workflow.outputs`` map names to
context paths without requiring every map value to be wrapped in
``{{ }}``.

Why custom (not Jinja2 / string.Template):
- The spec disallows new dependencies without justification, and
  the resolver is small enough to keep dependency-free.
- The substitution grammar is intentionally narrow: it cannot
  evaluate arbitrary Python, only dotted-path lookups against the
  context. This is a feature, not a limitation — it prevents
  workflow definitions from accidentally hosting code execution.
"""

from __future__ import annotations

import re
from typing import Any

from workflows.models import WorkflowContext

# Matches {{ path }} where path is a non-whitespace, non-brace
# dotted identifier (variables.x, outputs.s1.text, etc.).
_TEMPLATE_RE = re.compile(r"\{\{\s*([\w./]+)\s*\}\}")
# Matches a bare dotted path starting with a known namespace.
_BARE_PATH_RE = re.compile(r"^(variables|outputs)\.[\w./]+$")


def _resolve_path(path: str, context: WorkflowContext) -> Any:
    """Resolve a dotted path against a WorkflowContext.

    Recognized top-level namespaces:
    - ``variables.<name>``: look up in ``context.variables``.
    - ``outputs.<step_id>.<key>``: look up in ``context.step_outputs``.

    Raises ``KeyError`` if the path cannot be resolved; ``None`` if
    the leaf value is explicitly missing.
    """
    parts = path.split(".")
    if not parts:
        raise KeyError(f"Empty path in template expression: {path!r}")

    head = parts[0]
    if head == "variables":
        if len(parts) < 2:
            raise KeyError(f"variables path missing name: {path!r}")
        name = parts[1]
        if name not in context.variables:
            raise KeyError(f"Variable not found: {name!r}")
        return context.variables[name]

    if head == "outputs":
        if len(parts) < 3:
            raise KeyError(f"outputs path must be outputs.<step_id>.<key>: {path!r}")
        step_id = parts[1]
        key = parts[2]
        if step_id not in context.step_outputs:
            raise KeyError(f"Step output not found: {step_id!r}")
        step_out = context.step_outputs[step_id]
        if key not in step_out:
            raise KeyError(f"Step output key not found: {step_id}.{key!r}")
        return step_out[key]

    raise KeyError(f"Unknown template namespace: {head!r} (in {path!r})")


def _looks_like_path(value: str) -> bool:
    """Return True if ``value`` is a bare reference path we should resolve.

    Only values starting with ``variables.`` or ``outputs.`` qualify
    — anything else is treated as a literal string so workflow
    descriptions, free-form text, etc. are not misinterpreted.
    """
    return bool(_BARE_PATH_RE.match(value))


def resolve_value(value: Any, context: WorkflowContext) -> Any:
    """Recursively substitute template expressions in ``value``.

    - ``dict``: substitute in every value.
    - ``list``/``tuple``: substitute in every element (returns list).
    - ``str``: substitute any ``{{ ... }}`` occurrence. A bare
      dotted path (``variables.x`` / ``outputs.s1.text``) is also
      resolved without braces. If the whole string is exactly one
      expression, return the resolved value verbatim (not coerced
      to str) so callers can preserve ints, dicts, etc.
    - anything else: returned unchanged.

    A missing path raises ``KeyError``; the caller decides whether
    that is fatal or should produce a literal ``None``.
    """
    if isinstance(value, dict):
        return {k: resolve_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, context) for v in value]
    if isinstance(value, tuple):
        return [resolve_value(v, context) for v in value]
    if isinstance(value, str):
        # Fast path: string with no template marker at all and not a path.
        if "{{" not in value and not _looks_like_path(value):
            return value

        # If the whole string is one expression, return the raw value.
        full = _TEMPLATE_RE.fullmatch(value)
        if full is not None:
            return _resolve_path(full.group(1), context)

        # Bare path with no braces — return the resolved value. If the
        # path can't be resolved we propagate the KeyError so callers
        # using ``resolve_optional`` see ``None`` rather than the raw
        # path string.
        if _looks_like_path(value):
            return _resolve_path(value, context)

        # Otherwise substitute every occurrence and stringify.
        def _sub(match: "re.Match[str]") -> str:
            try:
                resolved = _resolve_path(match.group(1), context)
            except KeyError:
                # Unresolved expression — leave the marker visible so
                # the user notices a typo rather than getting "".
                return match.group(0)
            return "" if resolved is None else str(resolved)

        return _TEMPLATE_RE.sub(_sub, value)
    return value


def resolve_optional(value: Any, context: WorkflowContext) -> Any:
    """Like :func:`resolve_value` but missing paths become ``None``."""
    try:
        return resolve_value(value, context)
    except KeyError:
        return None
