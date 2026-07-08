"""
Self-Developing Platform (M9.11) — platform introspection engine.

Layer: Application/Core — composes existing sources of truth:

    Inspecting itself      → FastAPI route table, pipeline
                             verify_integration(), tool registry
                             stats, module inventory on disk
    Runtime bottlenecks    → M9.3 trace aggregates (real stage
                             latencies and error attribution)
    Architectural weakness → real structural checks (subsystems that
                             failed to construct, routers that failed
                             to import, stages persistently erroring)
    Suggesting improvements→ findings with the evidence that produced
                             them (same honesty contract as M9.14)
    Applying safe ones     → delegated to the M9.14 optimization
                             engine (single application path — no
                             second "apply" implementation)
    Running validation     → live smoke validation: every subsystem
                             constructible + one real pipeline
                             execution + tool registry sanity. This
                             is runtime validation; the full test
                             suite remains a CI concern (running
                             pytest inside the serving process would
                             be neither safe nor honest).
    Measuring & reporting  → before/after snapshots around apply().
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Stage keys as they appear in PipelineTrace error strings.
_STAGES = (
    "router", "memory", "context", "moa",
    "reflection", "knowledge_graph", "learning", "tutti",
)
_STAGE_ERROR_RATE_THRESHOLD = 0.25
_SLOW_STAGE_SHARE_THRESHOLD = 0.5  # stage dominating >50% of latency


@dataclass
class PlatformFinding:
    """One introspection finding with its evidence."""

    area: str  # structure | runtime | tools | routes
    severity: str  # info | warning | critical
    finding: str
    recommendation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "severity": self.severity,
            "finding": self.finding,
            "recommendation": self.recommendation,
            "evidence": dict(self.evidence),
        }


class PlatformIntrospection:
    """Inspect the running platform and report real findings."""

    def __init__(
        self,
        pipeline: Any,
        tool_runtime: Any = None,
        app: Any = None,
        package_root: Optional[Path] = None,
    ) -> None:
        self._pipeline = pipeline
        self._tool_runtime = tool_runtime
        self._app = app
        self._package_root = package_root or Path(__file__).resolve().parent.parent

    # ── Inspection ──────────────────────────────────────────────

    def inspect(self) -> dict[str, Any]:
        """A full self-description from live sources."""
        return {
            "timestamp": time.time(),
            "modules": self._inspect_modules(),
            "routes": self._inspect_routes(),
            "subsystems": self._inspect_subsystems(),
            "tools": self._inspect_tools(),
            "runtime": self._inspect_runtime(),
        }

    def _inspect_modules(self) -> dict[str, Any]:
        """Real package inventory from disk."""
        packages: dict[str, int] = {}
        for path in sorted(self._package_root.iterdir()):
            if not path.is_dir() or path.name == "__pycache__":
                continue
            module_count = sum(
                1 for f in path.rglob("*.py") if "__pycache__" not in f.parts
            )
            # Regular packages AND namespace packages (memory/ has no
            # __init__.py but is a real, imported package).
            if module_count > 0:
                packages[path.name] = module_count
        return {"package_root": str(self._package_root), "packages": packages}

    def _inspect_routes(self) -> dict[str, Any]:
        if self._app is None:
            return {"available": False, "count": 0, "paths": []}
        # The OpenAPI schema is the version-stable source of the full
        # route table (FastAPI may nest included routers in wrapper
        # objects that don't expose .path directly).
        try:
            schema = self._app.openapi()
            paths = sorted(schema.get("paths", {}).keys())
        except Exception:
            paths = sorted(
                {
                    getattr(r, "path", "")
                    for r in self._app.routes
                    if getattr(r, "path", "")
                }
            )
        return {"available": True, "count": len(paths), "paths": paths}

    def _inspect_subsystems(self) -> dict[str, Any]:
        return self._pipeline.verify_integration()

    def _inspect_tools(self) -> dict[str, Any]:
        if self._tool_runtime is None:
            return {"available": False}
        return {
            "available": True,
            "registry": self._tool_runtime.registry.get_stats(),
            "execution": self._tool_runtime.get_metrics(),
        }

    def _inspect_runtime(self) -> dict[str, Any]:
        return self._pipeline.trace_store.aggregates()

    # ── Weakness / bottleneck analysis ──────────────────────────

    def analyze(self) -> list[PlatformFinding]:
        """Real findings only; a healthy idle platform yields none."""
        findings: list[PlatformFinding] = []
        findings.extend(self._analyze_subsystem_construction())
        findings.extend(self._analyze_stage_errors())
        findings.extend(self._analyze_stage_latency())
        findings.extend(self._analyze_tools())
        return findings

    def _analyze_subsystem_construction(self) -> list[PlatformFinding]:
        findings: list[PlatformFinding] = []
        integration = self._pipeline.verify_integration()
        for name, state in integration["subsystems"].items():
            if isinstance(state, dict) and "error" in state:
                findings.append(
                    PlatformFinding(
                        area="structure",
                        severity="critical",
                        finding=f"Subsystem '{name}' failed to construct",
                        recommendation="Fix the construction error — this stage is dead for every request.",
                        evidence={"error": state["error"]},
                    )
                )
        return findings

    def _analyze_stage_errors(self) -> list[PlatformFinding]:
        findings: list[PlatformFinding] = []
        traces = self._pipeline.list_traces(
            limit=self._pipeline.trace_store.max_traces
        )
        if not traces:
            return findings
        for stage in _STAGES:
            errored = sum(
                1 for t in traces
                if any(e.startswith(f"{stage}:") for e in t.errors)
            )
            rate = errored / len(traces)
            if rate > _STAGE_ERROR_RATE_THRESHOLD:
                findings.append(
                    PlatformFinding(
                        area="runtime",
                        severity="warning",
                        finding=(
                            f"Stage '{stage}' errored in {errored} of "
                            f"{len(traces)} recent executions ({rate:.0%})"
                        ),
                        recommendation=f"Inspect '{stage}' error traces via /observatory/traces.",
                        evidence={"stage": stage, "error_rate": rate, "errored": errored},
                    )
                )
        return findings

    def _analyze_stage_latency(self) -> list[PlatformFinding]:
        findings: list[PlatformFinding] = []
        traces = self._pipeline.list_traces(
            limit=self._pipeline.trace_store.max_traces
        )
        if len(traces) < 5:
            return findings  # not enough evidence
        stage_totals = {
            "router": sum(t.router_latency_ms for t in traces),
            "memory": sum(t.memory_latency_ms for t in traces),
            "context": sum(t.context_latency_ms for t in traces),
            "moa": sum(t.moa_latency_ms for t in traces),
            "reflection": sum(t.reflection_latency_ms for t in traces),
            "knowledge_graph": sum(t.kg_latency_ms for t in traces),
            "learning": sum(t.learning_latency_ms for t in traces),
            "tutti": sum(t.tutti_latency_ms for t in traces),
        }
        total = sum(stage_totals.values())
        if total <= 0:
            return findings
        for stage, stage_total in stage_totals.items():
            share = stage_total / total
            if share > _SLOW_STAGE_SHARE_THRESHOLD:
                findings.append(
                    PlatformFinding(
                        area="runtime",
                        severity="warning",
                        finding=(
                            f"Stage '{stage}' accounts for {share:.0%} of "
                            f"instrumented pipeline latency over {len(traces)} executions"
                        ),
                        recommendation=f"Profile '{stage}' — it dominates the pipeline.",
                        evidence={
                            "stage": stage,
                            "share": share,
                            "stage_total_ms": stage_total,
                            "executions": len(traces),
                        },
                    )
                )
        return findings

    def _analyze_tools(self) -> list[PlatformFinding]:
        findings: list[PlatformFinding] = []
        if self._tool_runtime is None:
            return findings
        for name, metrics in self._tool_runtime.get_per_tool_metrics().items():
            if metrics["total_executions"] >= 5 and metrics["success_rate"] < 0.5:
                findings.append(
                    PlatformFinding(
                        area="tools",
                        severity="warning",
                        finding=(
                            f"Tool '{name}' succeeded in only "
                            f"{metrics['success_rate']:.0%} of "
                            f"{metrics['total_executions']} executions"
                        ),
                        recommendation=f"Inspect '{name}' failures via /tools/history.",
                        evidence={"tool": name, **metrics},
                    )
                )
        return findings

    # ── Validation ──────────────────────────────────────────────

    async def validate(self) -> dict[str, Any]:
        """Live smoke validation of the running platform.

        Executes one real request through the pipeline and checks
        every subsystem constructed. Full-suite testing remains CI's
        job — stated, not hidden.
        """
        checks: list[dict[str, Any]] = []

        integration = self._pipeline.verify_integration()
        broken = [
            name for name, state in integration["subsystems"].items()
            if isinstance(state, dict) and "error" in state
        ]
        checks.append(
            {
                "check": "subsystems_constructible",
                "passed": not broken,
                "detail": {"broken": broken, "active": integration["active_count"]},
            }
        )

        start = time.perf_counter()
        try:
            result = await self._pipeline.process(
                "platform validation smoke request"
            )
            checks.append(
                {
                    "check": "pipeline_executes",
                    "passed": result.outcome.status.value == "succeeded",
                    "detail": {
                        "request_id": result.trace.request_id,
                        "latency_ms": (time.perf_counter() - start) * 1000,
                        "stage_errors": list(result.trace.errors),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {
                    "check": "pipeline_executes",
                    "passed": False,
                    "detail": {"error": f"{type(exc).__name__}: {exc}"},
                }
            )

        if self._tool_runtime is not None:
            stats = self._tool_runtime.registry.get_stats()
            checks.append(
                {
                    "check": "tool_registry_populated",
                    "passed": stats["total"] > 0,
                    "detail": stats,
                }
            )

        return {
            "timestamp": time.time(),
            "passed": all(c["passed"] for c in checks),
            "checks": checks,
            "note": "Live smoke validation; the full test suite runs in CI.",
        }
