"""
Intelligent Auto Integration (M9.17).

Layer: Adapters/Infrastructure — composes the M9.26 AdapterRegistry
(the single integration contract) and the shared pipeline (optional
advisory notes).

Capabilities mapped honestly:

    Compatibility analysis → structural analysis of a candidate
                             technology description against the M9.26
                             category interfaces; for LIVE objects,
                             AdapterRegistry.validate() gives an
                             exact method-level verdict.
    Adapter generation     → generates a REAL, syntactically valid
                             Python adapter scaffold implementing the
                             category's required interface, with each
                             method delegating to a wrapped target
                             (mapped where names match, explicit
                             NotImplementedError with guidance where
                             they don't). Generated code is returned
                             to the caller — it is NEVER imported or
                             executed by the server (that would be
                             arbitrary code execution).
    Integration planning   → step plan referencing the exact contract.
    Validation             → the generated scaffold is validated by
                             parsing (ast) and by checking it declares
                             every required method; live-object
                             integrations are validated by the
                             registry's structural validator.
    Reporting              → every analysis/generation is persisted.

Known technologies (LongCat, MOA, Prompt Master, Agent Skills) get
curated capability mappings; unknown ones are analyzed from their
declared capability list.
"""

from __future__ import annotations

import ast
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from infrastructure.adapters import CATEGORY_SPECS, AdapterRegistry

# Curated capability → adapter-category mappings for the technologies
# the spec names. These reflect what those systems actually are.
_KNOWN_TECHNOLOGIES: dict[str, dict[str, Any]] = {
    "longcat": {
        "categories": ["memory"],
        "note": "LongCat is a hierarchical memory engine — Agent Reach already embeds one (memory/longcat.py); external LongCat variants integrate as memory adapters.",
    },
    "moa": {
        "categories": ["plugin"],
        "note": "Mixture-of-Agents orchestration — Agent Reach embeds an MOA engine (moa/engine.py); external MOA variants integrate as plugins.",
    },
    "prompt master": {
        "categories": ["plugin"],
        "note": "Prompt optimization systems integrate as plugins feeding the M9.20 evolution engine via propose_external().",
    },
    "agent skills": {
        "categories": ["plugin", "tool"],
        "note": "Skill frameworks integrate as plugins or individual async tools.",
    },
}

_CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "memory": ("memory", "recall", "storage", "retrieval", "rag"),
    "context": ("context", "window", "token budget"),
    "router": ("routing", "router", "model selection"),
    "tool": ("tool", "function call", "action"),
    "provider": ("provider", "llm api", "model api", "inference"),
    "plugin": ("plugin", "extension", "framework", "orchestration", "agent"),
}


@dataclass
class IntegrationReport:
    """One persisted analysis/generation report."""

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    technology: str = ""
    created_at: float = field(default_factory=time.time)
    kind: str = "analysis"  # analysis | generation
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "technology": self.technology,
            "created_at": self.created_at,
            "kind": self.kind,
            "payload": dict(self.payload),
        }


def generate_adapter_scaffold(
    category: str,
    technology_name: str,
    target_methods: Optional[dict[str, str]] = None,
) -> str:
    """Generate a real, parseable adapter class for a category.

    ``target_methods`` maps required-method → the wrapped target's
    method name. Unmapped methods raise NotImplementedError with
    precise guidance, so the scaffold is honest about its gaps.
    """
    spec = CATEGORY_SPECS.get(category)
    if spec is None:
        raise ValueError(f"Unknown category '{category}'. Valid: {sorted(CATEGORY_SPECS)}")
    mapping = dict(target_methods or {})
    class_name = (
        "".join(part.capitalize() for part in technology_name.replace("-", " ").split())
        or "Generated"
    ) + f"{category.capitalize()}Adapter"

    lines = [
        f'"""Generated {category} adapter for {technology_name} (M9.17).',
        "",
        "Wraps a target object behind the Agent Reach adapter contract.",
        "Review, complete the unmapped methods, test, then register via",
        "AdapterRegistry.register() — validation runs there.",
        '"""',
        "",
        "from typing import Any",
        "",
        "",
        f"class {class_name}:",
        f'    """Adapter binding {technology_name} to the \'{category}\' contract."""',
        "",
        "    def __init__(self, target: Any) -> None:",
        "        self._target = target",
        "",
    ]
    for method in spec.methods:
        prefix = "async def" if method.must_be_async else "def"
        name = method.name
        signature = (
            f"    {prefix} {name}(self, *args: Any, **kwargs: Any) -> Any:"
        )
        lines.append(signature)
        target = mapping.get(name)
        if target:
            call = f"self._target.{target}(*args, **kwargs)"
            body = f"        return await {call}" if method.must_be_async else f"        return {call}"
            lines.append(f'        """Delegates to target.{target}()."""')
            lines.append(body)
        else:
            lines.append(
                f'        """TODO: map to the {technology_name} equivalent of '
                f"'{name}' and delegate.\"\"\""
            )
            lines.append(
                f"        raise NotImplementedError("
                f"\"Map '{name}' to a {technology_name} operation before use\")"
            )
        lines.append("")
    return "\n".join(lines)


def validate_scaffold(category: str, source: str) -> list[str]:
    """Validate generated (or edited) scaffold source.

    Static only — the server never executes candidate code. Checks:
    parseability, one class present, every required method declared
    with the right async-ness.
    """
    spec = CATEGORY_SPECS.get(category)
    if spec is None:
        return [f"Unknown category '{category}'"]
    problems: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"SyntaxError: {exc.msg} (line {exc.lineno})"]

    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if not classes:
        return ["No class definition found"]
    cls = classes[0]
    methods = {
        n.name: n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method in spec.methods:
        node = methods.get(method.name)
        if node is None:
            problems.append(f"missing required method '{method.name}'")
        elif method.must_be_async and not isinstance(node, ast.AsyncFunctionDef):
            problems.append(f"method '{method.name}' must be async")
    return problems


class AutoIntegrationEngine:
    """Analyze technologies and generate validated adapter scaffolds."""

    def __init__(self, adapter_registry: AdapterRegistry, pipeline: Any = None) -> None:
        self._adapter_registry = adapter_registry
        self._pipeline = pipeline
        self._reports: dict[str, IntegrationReport] = {}

    # ── Compatibility analysis ──────────────────────────────────

    def analyze(
        self, technology: str, capabilities: Optional[list[str]] = None
    ) -> IntegrationReport:
        """Analyze a technology by name (+ declared capabilities)."""
        if not technology.strip():
            raise ValueError("technology name must not be empty")
        name = technology.strip()
        known = _KNOWN_TECHNOLOGIES.get(name.lower())

        if known:
            categories = list(known["categories"])
            basis = "curated"
            note = known["note"]
        else:
            declared = " ".join(capabilities or []).lower()
            categories = sorted(
                category
                for category, keywords in _CAPABILITY_KEYWORDS.items()
                if any(keyword in declared for keyword in keywords)
            )
            basis = "declared_capabilities"
            note = (
                "Mapped from declared capabilities via the documented keyword "
                "vocabulary." if categories else
                "No declared capability matched an adapter category — provide "
                "capabilities or integrate as a plugin."
            )

        contract_details = {
            category: {
                "required_interface": [
                    {"name": m.name, "async": m.must_be_async}
                    for m in CATEGORY_SPECS[category].methods
                ],
            }
            for category in categories
        }
        report = IntegrationReport(
            technology=name,
            kind="analysis",
            payload={
                "basis": basis,
                "note": note,
                "candidate_categories": categories,
                "contracts": contract_details,
                "integration_plan": [
                    "1. Generate an adapter scaffold per candidate category "
                    "(POST /auto-integration/generate).",
                    "2. Complete the unmapped delegations against the real SDK.",
                    "3. Validate statically (POST /auto-integration/validate).",
                    "4. Register + activate through the M9.26 AdapterRegistry.",
                ],
            },
        )
        self._reports[report.report_id] = report
        return report

    def analyze_object(self, technology: str, candidate: Any) -> IntegrationReport:
        """Exact method-level compatibility of a LIVE object against
        every category, via the registry's structural validator."""
        results = {
            category: self._adapter_registry.validate(category, candidate)
            for category in CATEGORY_SPECS
        }
        compatible = sorted(c for c, problems in results.items() if not problems)
        report = IntegrationReport(
            technology=technology,
            kind="analysis",
            payload={
                "basis": "live_object",
                "compatible_categories": compatible,
                "problems_by_category": {
                    c: problems for c, problems in results.items() if problems
                },
            },
        )
        self._reports[report.report_id] = report
        return report

    # ── Generation & validation ─────────────────────────────────

    def generate(
        self,
        technology: str,
        category: str,
        target_methods: Optional[dict[str, str]] = None,
    ) -> IntegrationReport:
        """Generate a validated adapter scaffold (never executed here)."""
        source = generate_adapter_scaffold(category, technology, target_methods)
        problems = validate_scaffold(category, source)
        report = IntegrationReport(
            technology=technology,
            kind="generation",
            payload={
                "category": category,
                "source": source,
                "validation_problems": problems,
                "valid": not problems,
                "note": "Generated code is returned for review — the server never executes it.",
            },
        )
        self._reports[report.report_id] = report
        return report

    # ── Reports ─────────────────────────────────────────────────

    def get_report(self, report_id: str) -> Optional[IntegrationReport]:
        return self._reports.get(report_id)

    def list_reports(self, limit: int = 20) -> list[IntegrationReport]:
        reports = sorted(
            self._reports.values(), key=lambda r: r.created_at, reverse=True
        )
        return reports[: max(0, limit)]

    def clear(self) -> None:
        self._reports.clear()
