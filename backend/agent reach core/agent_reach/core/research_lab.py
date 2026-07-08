"""
AI Research Laboratory (M9.28).

Layer: Application/Core — controlled experimentation composed from
EXISTING engines. An experiment is a set of named variants executed
against the same task list, with real measurements per variant:

    pipeline_config → variants are PipelineConfig overrides; each
                      variant builds an IntelligentPipeline (same
                      composition path as production) and runs the
                      tasks through it. Measured: latency, stage
                      errors, reflection scores.
    prompt          → variants are prompt templates; each task is
                      rendered through the M7 PromptLibrary and run
                      through the SHARED pipeline. Measured: latency,
                      outcome status, answer length.
    memory_policy   → variants are M9.21 MemoryPolicy parameter sets
                      applied to fresh LongCat engines seeded with
                      the same synthetic workload. Measured: real
                      before/after memory counts from optimize().

Controlled means controlled: variants run against identical task
lists, results carry every raw measurement, and the "winner" is
declared only on the experiment's stated metric with the comparison
data attached. No invented scores.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


_SUPPORTED_KINDS = ("pipeline_config", "prompt", "memory_policy")


@dataclass
class Experiment:
    """One controlled experiment definition + its results."""

    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = ""
    name: str = ""
    tasks: list[str] = field(default_factory=list)
    variants: dict[str, dict[str, Any]] = field(default_factory=dict)
    metric: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    winner: Optional[str] = None
    status: str = "pending"  # pending | completed | failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "kind": self.kind,
            "name": self.name,
            "tasks": list(self.tasks),
            "variants": {k: dict(v) for k, v in self.variants.items()},
            "metric": self.metric,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "results": {k: dict(v) for k, v in self.results.items()},
            "winner": self.winner,
            "status": self.status,
        }


class ResearchLab:
    """Define and run controlled experiments on existing engines."""

    def __init__(self, max_experiments: int = 100) -> None:
        if max_experiments < 1:
            raise ValueError("max_experiments must be >= 1")
        self._experiments: dict[str, Experiment] = {}
        self._max_experiments = max_experiments

    # ── Definition ──────────────────────────────────────────────

    def define(
        self,
        kind: str,
        name: str,
        tasks: list[str],
        variants: dict[str, dict[str, Any]],
        metric: str = "",
    ) -> Experiment:
        """Define an experiment. Strictly validated."""
        if kind not in _SUPPORTED_KINDS:
            raise ValueError(
                f"Unsupported kind '{kind}'. Supported: {list(_SUPPORTED_KINDS)}"
            )
        if not name.strip():
            raise ValueError("experiment name must not be empty")
        if not tasks:
            raise ValueError("at least one task is required")
        if len(variants) < 2:
            raise ValueError("an experiment needs at least two variants")

        default_metrics = {
            "pipeline_config": "avg_latency_ms",
            "prompt": "avg_latency_ms",
            "memory_policy": "total_after",
        }
        experiment = Experiment(
            kind=kind,
            name=name.strip(),
            tasks=list(tasks),
            variants={k: dict(v) for k, v in variants.items()},
            metric=metric or default_metrics[kind],
        )
        self._experiments[experiment.experiment_id] = experiment
        self._evict()
        return experiment

    # ── Execution ───────────────────────────────────────────────

    async def run(self, experiment_id: str) -> Experiment:
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise KeyError(f"Experiment '{experiment_id}' not found")

        runners = {
            "pipeline_config": self._run_pipeline_config_variant,
            "prompt": self._run_prompt_variant,
            "memory_policy": self._run_memory_policy_variant,
        }
        runner = runners[experiment.kind]

        try:
            for variant_name, variant_params in experiment.variants.items():
                experiment.results[variant_name] = await runner(
                    experiment, variant_params
                )
            experiment.winner = self._pick_winner(experiment)
            experiment.status = "completed"
        except Exception as exc:  # noqa: BLE001 — experiment isolation
            experiment.status = "failed"
            experiment.results["__error__"] = {
                "error": f"{type(exc).__name__}: {exc}"
            }
        experiment.finished_at = time.time()
        return experiment

    async def _run_pipeline_config_variant(
        self, experiment: Experiment, params: dict[str, Any]
    ) -> dict[str, Any]:
        from composition import build_intelligent_pipeline
        from core.intelligent_pipeline import PipelineConfig

        valid_fields = set(PipelineConfig.__dataclass_fields__)
        unknown = [k for k in params if k not in valid_fields]
        if unknown:
            raise ValueError(f"Unknown PipelineConfig fields: {unknown}")

        pipeline = build_intelligent_pipeline(config=PipelineConfig(**params))
        latencies: list[float] = []
        errors = 0
        reflection_scores: list[float] = []
        request_ids: list[str] = []
        for task in experiment.tasks:
            result = await pipeline.process(task)
            latencies.append(result.trace.total_latency_ms)
            errors += 1 if result.trace.errors else 0
            if result.trace.reflection_active:
                reflection_scores.append(result.trace.reflection_score)
            request_ids.append(result.trace.request_id)
        return {
            "tasks_run": len(latencies),
            "avg_latency_ms": sum(latencies) / len(latencies),
            "max_latency_ms": max(latencies),
            "error_count": errors,
            "avg_reflection_score": (
                sum(reflection_scores) / len(reflection_scores)
                if reflection_scores
                else None
            ),
            "request_ids": request_ids,
        }

    async def _run_prompt_variant(
        self, experiment: Experiment, params: dict[str, Any]
    ) -> dict[str, Any]:
        from composition import build_intelligent_pipeline
        from prompts.library import PromptLibrary

        template = str(params.get("template", ""))
        if not template:
            raise ValueError("prompt variants need a 'template' parameter")

        library = PromptLibrary()
        library.register("__experiment__", template)
        pipeline = build_intelligent_pipeline()

        latencies: list[float] = []
        answer_lengths: list[int] = []
        succeeded = 0
        for task in experiment.tasks:
            rendered = library.render("__experiment__", {"task": task})
            result = await pipeline.process(rendered)
            latencies.append(result.trace.total_latency_ms)
            answer_lengths.append(len(result.outcome.answer))
            succeeded += 1 if result.outcome.status.value == "succeeded" else 0
        return {
            "tasks_run": len(latencies),
            "avg_latency_ms": sum(latencies) / len(latencies),
            "success_rate": succeeded / len(latencies),
            "avg_answer_length": sum(answer_lengths) / len(answer_lengths),
        }

    async def _run_memory_policy_variant(
        self, experiment: Experiment, params: dict[str, Any]
    ) -> dict[str, Any]:
        from memory.adaptive import AdaptiveMemoryManager, MemoryPolicy
        from memory.longcat import LongCatMemoryEngine

        engine = LongCatMemoryEngine()
        # identical seeded workload per variant: the task list itself
        for index, task in enumerate(experiment.tasks):
            engine.store(
                task,
                importance=(index % 10) / 10.0,
                metadata={"session_id": f"s{index % 3}"},
                add_to_working=False,
            )
        manager = AdaptiveMemoryManager(engine, MemoryPolicy(**params))
        report = manager.optimize()
        return {
            "seeded": len(experiment.tasks),
            "consolidated": report.consolidated,
            "archived": report.archived,
            "deleted": report.deleted,
            "compressed_sessions": len(report.compressed_sessions),
            "total_before": report.before.get("total", 0),
            "total_after": report.after.get("total", 0),
        }

    # ── Winner selection ────────────────────────────────────────

    @staticmethod
    def _pick_winner(experiment: Experiment) -> Optional[str]:
        """Winner on the stated metric only; lower-is-better for
        latency/error metrics, higher-is-better otherwise."""
        metric = experiment.metric
        lower_is_better = metric.endswith("latency_ms") or metric in (
            "error_count", "total_after",
        )
        scored = [
            (name, results.get(metric))
            for name, results in experiment.results.items()
            if not name.startswith("__") and results.get(metric) is not None
        ]
        if not scored:
            return None
        return (min if lower_is_better else max)(scored, key=lambda p: p[1])[0]

    # ── Introspection ───────────────────────────────────────────

    def get(self, experiment_id: str) -> Optional[Experiment]:
        return self._experiments.get(experiment_id)

    def list_experiments(self, limit: int = 20) -> list[Experiment]:
        experiments = sorted(
            self._experiments.values(), key=lambda e: e.created_at, reverse=True
        )
        return experiments[: max(0, limit)]

    def clear(self) -> None:
        self._experiments.clear()

    def _evict(self) -> None:
        while len(self._experiments) > self._max_experiments:
            oldest = min(self._experiments.values(), key=lambda e: e.created_at)
            del self._experiments[oldest.experiment_id]
