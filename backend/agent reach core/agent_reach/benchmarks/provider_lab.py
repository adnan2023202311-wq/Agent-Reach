"""
Autonomous Benchmark Laboratory (M9.19).

Layer: Application — composes EXISTING machinery:

- provider execution → same ProviderManager client factories the
  playground uses (injectable factory for tests)
- routing updates    → ReachIntelligenceRouter's OWN benchmark cache
  (set_benchmark) and stats (record_success / record_failure), so
  scoring and learn_from_history() incorporate lab results with no
  new routing code
- cost model         → the router's per-provider cost table

Measurement honesty
-------------------
Quality is only ever scored against VERIFIABLE tasks: every task in
the default suite has a deterministic checker (exact answers,
required substrings). quality = fraction of checks passed. There is
no subjective scoring and no fabricated number: an unconfigured
provider produces an honest "not benchmarked" entry, not a zero that
poisons routing.

Categories cover the spec list that is verifiable without human
judgment: reasoning, coding, tool_use (structured-output emission),
long_context (retrieval from a long document). Latency and cost are
measured/estimated per call.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from infrastructure.provider_manager import (
    SUPPORTED_PROVIDERS,
    ProviderManager,
    _DEFAULT_MODELS,
)
from routing.router import ReachIntelligenceRouter

_SETTINGS_TO_MANAGER: dict[str, str] = {"google": "gemini"}
_CHARS_PER_TOKEN = 4.0


@dataclass
class BenchmarkTask:
    """One verifiable benchmark task."""

    task_id: str
    category: str  # reasoning | coding | tool_use | long_context
    prompt: str
    checker: Callable[[str], bool]
    description: str = ""


def _contains_all(*needles: str) -> Callable[[str], bool]:
    lowered = [n.lower() for n in needles]

    def check(output: str) -> bool:
        text = output.lower()
        return all(n in text for n in lowered)

    return check


def default_task_suite() -> list[BenchmarkTask]:
    """The built-in verifiable task suite.

    Deliberately small and deterministic: each task has one objective
    check. Extend via ProviderBenchmarkLab(tasks=...).
    """
    long_document = (
        "Quarterly report. " * 120
        + "The access code for the vault is BLUE-MARBLE-47. "
        + "End of report. " * 120
    )
    return [
        BenchmarkTask(
            task_id="reasoning_arithmetic",
            category="reasoning",
            prompt=(
                "A train travels 60 km in 45 minutes. What is its speed in "
                "km/h? Answer with the number only."
            ),
            checker=_contains_all("80"),
            description="Unit-rate arithmetic with a single numeric answer.",
        ),
        BenchmarkTask(
            task_id="reasoning_logic",
            category="reasoning",
            prompt=(
                "All bloops are razzies. All razzies are lazzies. "
                "Is every bloop a lazzy? Answer 'yes' or 'no' only."
            ),
            checker=_contains_all("yes"),
            description="Two-step syllogism.",
        ),
        BenchmarkTask(
            task_id="coding_reverse",
            category="coding",
            prompt=(
                "Write a Python function named reverse_words that takes a "
                "sentence string and returns the words in reverse order. "
                "Reply with code only."
            ),
            checker=_contains_all("def reverse_words", "split", "return"),
            description="Small function with required structural elements.",
        ),
        BenchmarkTask(
            task_id="tool_use_json",
            category="tool_use",
            prompt=(
                'Emit exactly this tool call as JSON, nothing else: a call '
                'to a tool named "search" with the argument query set to '
                '"agent runtimes".'
            ),
            checker=_contains_all('"search"', '"query"', "agent runtimes"),
            description="Structured tool-call emission fidelity.",
        ),
        BenchmarkTask(
            task_id="long_context_retrieval",
            category="long_context",
            prompt=(
                "In the following document, find the access code and reply "
                f"with the code only.\n\n{long_document}"
            ),
            checker=_contains_all("blue-marble-47"),
            description="Needle retrieval from a long document.",
        ),
    ]


@dataclass
class ProviderBenchmarkReport:
    """Results of one provider's lab run."""

    provider: str
    configured: bool
    model: str = ""
    task_results: list[dict[str, Any]] = field(default_factory=list)
    quality: float = 0.0  # fraction of verifiable checks passed
    avg_latency_ms: float = 0.0
    cost_estimate_usd: float = 0.0
    error: Optional[str] = None
    per_category: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "model": self.model,
            "task_results": list(self.task_results),
            "quality": self.quality,
            "avg_latency_ms": self.avg_latency_ms,
            "cost_estimate_usd": self.cost_estimate_usd,
            "error": self.error,
            "per_category": dict(self.per_category),
        }


@dataclass
class LabRun:
    """One complete laboratory run across providers."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    reports: list[ProviderBenchmarkReport] = field(default_factory=list)
    routing_updates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "reports": [r.to_dict() for r in self.reports],
            "routing_updates": list(self.routing_updates),
        }


class ProviderBenchmarkLab:
    """Benchmark providers on verifiable tasks; update routing.

    Parameters
    ----------
    settings:
        Source of provider API keys.
    router:
        The SHARED ReachIntelligenceRouter whose benchmark cache and
        stats receive results. Injected — typically the pipeline's.
    tasks:
        Task suite; defaults to default_task_suite().
    client_factory:
        Test seam returning a ModelClient for a manager-name provider.
    timeout_seconds:
        Per-task timeout.
    """

    def __init__(
        self,
        settings: Any,
        router: ReachIntelligenceRouter,
        tasks: Optional[list[BenchmarkTask]] = None,
        client_factory: Optional[Any] = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._settings = settings
        self._router = router
        self._tasks = tasks if tasks is not None else default_task_suite()
        self._client_factory = client_factory
        self._timeout = timeout_seconds
        self._runs: list[LabRun] = []

    @property
    def tasks(self) -> list[BenchmarkTask]:
        return list(self._tasks)

    # ── Running ─────────────────────────────────────────────────

    async def run(self, providers: list[str]) -> LabRun:
        """Benchmark each provider and feed results into the router."""
        if not providers:
            raise ValueError("at least one provider is required")

        run = LabRun()
        reports = await asyncio.gather(
            *(self._benchmark_provider(p) for p in providers)
        )
        run.reports = list(reports)

        for report in run.reports:
            updates = self._apply_to_router(report)
            run.routing_updates.extend(updates)

        # Let the router re-derive its preference from the new stats.
        self._router.learn_from_history()
        if self._router.preferred_provider:
            run.routing_updates.append(
                {
                    "type": "preferred_provider",
                    "provider": self._router.preferred_provider,
                }
            )

        run.finished_at = time.time()
        self._runs.append(run)
        return run

    async def _benchmark_provider(self, provider: str) -> ProviderBenchmarkReport:
        manager_name = _SETTINGS_TO_MANAGER.get(provider, provider)
        report = ProviderBenchmarkReport(
            provider=provider,
            configured=False,
            model=_DEFAULT_MODELS.get(manager_name, ""),
        )

        if manager_name not in SUPPORTED_PROVIDERS:
            report.error = f"Provider '{provider}' is not supported"
            return report

        api_key = self._settings.provider_api_key(provider)
        if not api_key and self._client_factory is None:
            report.error = f"Provider '{provider}' is not configured — not benchmarked"
            return report

        report.configured = True
        try:
            client = self._build_client(manager_name, api_key)
        except Exception as exc:  # noqa: BLE001
            report.error = f"{type(exc).__name__}: {exc}"
            report.configured = False
            return report

        latencies: list[float] = []
        total_chars = 0
        passed_by_category: dict[str, list[bool]] = {}

        for task in self._tasks:
            entry: dict[str, Any] = {
                "task_id": task.task_id,
                "category": task.category,
            }
            start = time.perf_counter()
            try:
                output = await asyncio.wait_for(
                    client.complete(
                        [{"role": "user", "content": task.prompt}],
                        max_tokens=1024,
                    ),
                    timeout=self._timeout,
                )
                latency = (time.perf_counter() - start) * 1000
                passed = bool(task.checker(output))
                entry.update(
                    {
                        "passed": passed,
                        "latency_ms": latency,
                        "output_preview": output[:200],
                    }
                )
                latencies.append(latency)
                total_chars += len(task.prompt) + len(output)
                passed_by_category.setdefault(task.category, []).append(passed)
            except asyncio.TimeoutError:
                entry.update(
                    {"passed": False, "error": f"timed out after {self._timeout}s"}
                )
                passed_by_category.setdefault(task.category, []).append(False)
            except Exception as exc:  # noqa: BLE001
                entry.update(
                    {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
                )
                passed_by_category.setdefault(task.category, []).append(False)
            report.task_results.append(entry)

        checks = [r for results in passed_by_category.values() for r in results]
        report.quality = (
            sum(1 for c in checks if c) / len(checks) if checks else 0.0
        )
        report.avg_latency_ms = (
            sum(latencies) / len(latencies) if latencies else 0.0
        )
        report.per_category = {
            category: sum(1 for p in results if p) / len(results)
            for category, results in passed_by_category.items()
        }
        tokens = total_chars / _CHARS_PER_TOKEN
        report.cost_estimate_usd = round(
            ReachIntelligenceRouter.get_cost(manager_name) * tokens / 1000.0, 8
        )
        return report

    # ── Routing integration ─────────────────────────────────────

    def _apply_to_router(
        self, report: ProviderBenchmarkReport
    ) -> list[dict[str, Any]]:
        """Feed one report into the router's OWN benchmark/stat APIs.

        Unconfigured providers are skipped entirely — absent data
        must not poison routing.
        """
        if not report.configured:
            return []
        manager_name = _SETTINGS_TO_MANAGER.get(report.provider, report.provider)
        updates: list[dict[str, Any]] = []

        self._router.set_benchmark(manager_name, "quality", report.quality)
        self._router.set_benchmark(
            manager_name, "avg_latency_ms", report.avg_latency_ms
        )
        for category, score in report.per_category.items():
            self._router.set_benchmark(manager_name, f"quality_{category}", score)
        updates.append(
            {
                "type": "benchmark",
                "provider": manager_name,
                "quality": report.quality,
                "avg_latency_ms": report.avg_latency_ms,
                "per_category": dict(report.per_category),
            }
        )

        # Record real call outcomes into provider stats so
        # learn_from_history() sees them.
        for entry in report.task_results:
            if entry.get("passed") and "latency_ms" in entry:
                self._router.record_success(manager_name, entry["latency_ms"])
            elif "error" in entry:
                self._router.record_failure(manager_name, str(entry["error"]))
        updates.append(
            {
                "type": "stats",
                "provider": manager_name,
                "recorded_calls": len(report.task_results),
            }
        )
        return updates

    # ── History ─────────────────────────────────────────────────

    def get_runs(self, limit: int = 20) -> list[LabRun]:
        """Past lab runs, newest first."""
        return list(reversed(self._runs))[: max(0, limit)]

    def get_run(self, run_id: str) -> Optional[LabRun]:
        return next((r for r in self._runs if r.run_id == run_id), None)

    def clear(self) -> None:
        self._runs.clear()

    # ── Internals ───────────────────────────────────────────────

    def _build_client(self, manager_name: str, api_key: Optional[str]) -> Any:
        if self._client_factory is not None:
            return self._client_factory(manager_name)
        manager = ProviderManager(
            provider_keys={manager_name: api_key},
            default_provider=manager_name,
        )
        return manager._get_or_create_client(manager_name)
