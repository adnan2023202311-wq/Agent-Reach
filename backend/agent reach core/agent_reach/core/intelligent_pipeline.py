"""
Intelligent Pipeline (M7.5).

The unified execution pipeline that integrates every Milestone 7
subsystem into a single intelligent flow.

Layer: Application/Core.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from typing import TYPE_CHECKING

from core.controller import MainController
from domain.models import TaskExecutionOutcome, TaskStatus

if TYPE_CHECKING:  # pragma: no cover
    from core.trace_store import PipelineTraceStore

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Controls which M7 subsystems are active."""

    enable_router: bool = True
    enable_memory: bool = True
    enable_context: bool = True
    enable_moa: bool = True
    enable_reflection: bool = True
    enable_knowledge_graph: bool = True
    enable_learning: bool = True
    enable_tutti: bool = True
    moa_min_confidence: float = 0.7
    moa_min_providers: int = 2
    reflection_auto_retry: bool = True
    reflection_max_retries: int = 1
    memory_max_context_items: int = 20
    memory_add_to_working: bool = True


@dataclass
class PipelineTrace:
    """Full trace of decisions made during pipeline execution."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    router_provider: str = ""
    router_strategy: str = ""
    router_score: float = 0.0
    router_latency_ms: float = 0.0
    router_active: bool = False
    memory_items_retrieved: int = 0
    memory_working_size: int = 0
    memory_latency_ms: float = 0.0
    memory_active: bool = False
    context_tokens_used: int = 0
    context_budget: int = 0
    context_latency_ms: float = 0.0
    context_active: bool = False
    moa_mode: str = ""
    moa_providers: int = 0
    moa_confidence: float = 0.0
    moa_latency_ms: float = 0.0
    moa_active: bool = False
    reflection_score: float = 0.0
    reflection_insights: int = 0
    reflection_retried: bool = False
    reflection_latency_ms: float = 0.0
    reflection_active: bool = False
    kg_nodes_added: int = 0
    kg_edges_added: int = 0
    kg_latency_ms: float = 0.0
    kg_active: bool = False
    learning_recorded: bool = False
    learning_latency_ms: float = 0.0
    learning_active: bool = False
    tutti_export_id: str = ""
    tutti_latency_ms: float = 0.0
    tutti_active: bool = False
    total_latency_ms: float = 0.0
    final_answer: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "router": {"active": self.router_active, "provider": self.router_provider, "strategy": self.router_strategy, "score": self.router_score, "latency_ms": self.router_latency_ms},
            "memory": {"active": self.memory_active, "items_retrieved": self.memory_items_retrieved, "working_size": self.memory_working_size, "latency_ms": self.memory_latency_ms},
            "context": {"active": self.context_active, "tokens_used": self.context_tokens_used, "budget": self.context_budget, "latency_ms": self.context_latency_ms},
            "moa": {"active": self.moa_active, "mode": self.moa_mode, "providers": self.moa_providers, "confidence": self.moa_confidence, "latency_ms": self.moa_latency_ms},
            "reflection": {"active": self.reflection_active, "score": self.reflection_score, "insights": self.reflection_insights, "retried": self.reflection_retried, "latency_ms": self.reflection_latency_ms},
            "knowledge_graph": {"active": self.kg_active, "nodes_added": self.kg_nodes_added, "edges_added": self.kg_edges_added, "latency_ms": self.kg_latency_ms},
            "learning": {"active": self.learning_active, "recorded": self.learning_recorded, "latency_ms": self.learning_latency_ms},
            "tutti": {"active": self.tutti_active, "export_id": self.tutti_export_id, "latency_ms": self.tutti_latency_ms},
            "total_latency_ms": self.total_latency_ms,
            "errors": list(self.errors),
        }


@dataclass
class PipelineResult:
    """The outcome of an intelligent pipeline execution."""

    outcome: TaskExecutionOutcome
    trace: PipelineTrace
    tutti_export: Optional[dict[str, Any]] = None

    @property
    def answer(self) -> str:
        return self.outcome.answer

    @property
    def status(self) -> TaskStatus:
        return self.outcome.status


class IntelligentPipeline:
    """The unified intelligent execution pipeline.

    Wraps MainController and layers every M7 subsystem around it.
    """

    def __init__(
        self,
        controller: MainController,
        config: Optional[PipelineConfig] = None,
        trace_store: Optional["PipelineTraceStore"] = None,
        event_hub: Optional[Any] = None,
    ) -> None:
        self._controller = controller
        self._config = config or PipelineConfig()
        # M9.3: every execution trace is persisted so requests remain
        # observable and debuggable after they complete.
        from core.trace_store import PipelineTraceStore

        self._trace_store = trace_store or PipelineTraceStore()
        # M9.24: optional event hub — when present, the pipeline
        # publishes the canonical runtime event chain. None (default)
        # preserves pre-M9.24 behavior exactly.
        self._event_hub = event_hub
        self._router: Any = None
        self._memory: Any = None
        self._context_engine: Any = None
        self._moa: Any = None
        self._reflection: Any = None
        self._knowledge_graph: Any = None
        self._learning: Any = None
        self._tutti: Any = None
        self._total_requests: int = 0
        self._total_latency_ms: float = 0.0

    # ── Main entry ──────────────────────────────────────────────

    async def process(self, message: str, *, session_id: Optional[str] = None, extra_context: Optional[dict[str, Any]] = None) -> PipelineResult:
        """Process a user request through the full intelligent pipeline.

        M9 fix: ``extra_context`` may carry ``provider_id`` and
        ``model_id`` from the frontend topbar selector OR from a
        Swagger/REST client's top-level request fields (merged into
        ``extra_context`` by ChatRequest.effective_context /
        SendMessageRequest.effective_context). We apply them to the
        shared ProviderManager BEFORE dispatch so every agent in this
        turn uses the user-selected provider, not the backend's
        hardcoded default. Without this, the pipeline always ran
        through Anthropic even after the user selected OpenRouter or
        Google.
        """
        pipeline_start = time.perf_counter()
        trace = PipelineTrace()
        effective_message = message
        effective_session = session_id or "default"
        tutti_export: Optional[dict[str, Any]] = None

        # ── Provider override (M9 fix) ─────────────────────────────
        applied_provider: Optional[str] = None
        applied_model: Optional[str] = None
        if extra_context:
            ctx_provider = extra_context.get("provider_id") or extra_context.get("provider")
            ctx_model = extra_context.get("model_id") or extra_context.get("model")
            pm = self._get_provider_manager()
            if pm is not None and ctx_provider:
                # Normalize frontend/API name → runtime ProviderManager
                # name (e.g. "google" → "gemini"). See
                # conversation/engine.py's _to_runtime_provider_name.
                runtime_provider = _to_runtime_provider_name(ctx_provider)
                try:
                    pm.set_provider(runtime_provider)
                    applied_provider = runtime_provider
                    logger.info(
                        "Pipeline: applied user-selected provider override: %s (frontend) → %s (runtime)",
                        ctx_provider, runtime_provider,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Pipeline: could not switch to provider %r (runtime %r): %s — falling back to %s",
                        ctx_provider, runtime_provider, exc, pm.active_provider,
                    )
                if ctx_model and applied_provider:
                    try:
                        pm.set_model(applied_provider, ctx_model)
                        applied_model = ctx_model
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Pipeline: could not set model %r for provider %r: %s",
                            ctx_model, applied_provider, exc,
                        )
                if applied_provider:
                    trace.router_provider = applied_provider
                    trace.router_active = True
                    trace.router_strategy = "user-selected"

        try:
            effective_message = await self._step_router(effective_message, effective_session, trace)
            memory_context = await self._step_memory(effective_message, effective_session, trace)
            effective_message = await self._step_context(effective_message, effective_session, memory_context, trace)
            effective_message, _ = await self._step_moa(effective_message, trace)
            outcome = await self._controller.handle_request(effective_message)
            outcome = await self._step_reflection(outcome, effective_message, trace)
            await self._step_knowledge_graph(outcome, trace)
            await self._step_learning(outcome, effective_message, trace)
            tutti_export = await self._step_tutti(outcome, effective_message, effective_session, trace)
            trace.final_answer = outcome.answer
        except Exception as exc:
            logger.exception("Pipeline error: %s", exc)
            trace.errors.append(str(exc))
            outcome = await self._controller.handle_request(message)
            trace.final_answer = outcome.answer

        trace.total_latency_ms = (time.perf_counter() - pipeline_start) * 1000
        self._total_requests += 1
        self._total_latency_ms += trace.total_latency_ms

        # M9.3: persist the trace so /observatory can serve it later.
        self._trace_store.record(trace)

        # M9.24: publish the runtime event chain from the REAL trace.
        await self._publish_events(trace, effective_session)

        return PipelineResult(outcome=outcome, trace=trace, tutti_export=tutti_export if self._config.enable_tutti else None)

    def _get_provider_manager(self):
        """Reach the shared ProviderManager the controller's agents use.

        Mirrors ConversationEngine._get_provider_manager — see that
        method for the full reasoning. Returns None if the plumbing
        isn't reachable (e.g. test stubs), in which case the override
        is silently skipped.
        """
        try:
            dispatcher = getattr(self._controller, "_dispatcher", None)
            if dispatcher is None:
                return None
            agents = getattr(dispatcher, "_agents", None)
            if not agents:
                return None
            first_agent = next(iter(agents.values()))
            return getattr(first_agent, "_model_client", None)
        except Exception:  # noqa: BLE001
            return None

    async def _publish_events(self, trace: PipelineTrace, session_id: str) -> None:
        """Publish the M9.24 event chain for one completed execution.

        Every event carries the request_id, so subscribers (and the
        /events API) can join events back to the persisted trace.
        Publishing failures never break request processing.
        """
        if self._event_hub is None:
            return
        try:
            from core.runtime_events import RuntimeEvent

            base = {"request_id": trace.request_id, "session_id": session_id}
            await self._event_hub.publish(
                RuntimeEvent.PIPELINE_STARTED, {**base, "timestamp": trace.timestamp}
            )
            if trace.router_active:
                await self._event_hub.publish(
                    RuntimeEvent.ROUTER_DECIDED,
                    {**base, "provider": trace.router_provider},
                )
            if trace.memory_active:
                await self._event_hub.publish(
                    RuntimeEvent.MEMORY_UPDATED,
                    {**base, "items_retrieved": trace.memory_items_retrieved},
                )
            if trace.context_active:
                await self._event_hub.publish(
                    RuntimeEvent.CONTEXT_BUILT,
                    {**base, "tokens_used": trace.context_tokens_used},
                )
            if trace.kg_active:
                await self._event_hub.publish(
                    RuntimeEvent.KNOWLEDGE_UPDATED,
                    {
                        **base,
                        "nodes_added": trace.kg_nodes_added,
                        "edges_added": trace.kg_edges_added,
                    },
                )
            if trace.reflection_active:
                await self._event_hub.publish(
                    RuntimeEvent.REFLECTION_TRIGGERED,
                    {
                        **base,
                        "score": trace.reflection_score,
                        "retried": trace.reflection_retried,
                    },
                )
            if trace.learning_active:
                await self._event_hub.publish(
                    RuntimeEvent.LEARNING_TRIGGERED,
                    {**base, "recorded": trace.learning_recorded},
                )
            terminal = (
                RuntimeEvent.PIPELINE_FAILED
                if trace.errors
                else RuntimeEvent.PIPELINE_COMPLETED
            )
            await self._event_hub.publish(
                terminal,
                {
                    **base,
                    "latency_ms": trace.total_latency_ms,
                    "errors": list(trace.errors),
                },
            )
        except Exception as exc:  # noqa: BLE001 — events must never break requests
            logger.warning("Event publishing failed: %s", exc)

    # ── Steps ───────────────────────────────────────────────────

    async def _step_router(self, message: str, session_id: str, trace: PipelineTrace) -> str:
        # M9 fix: if the user explicitly selected a provider (stamped
        # in trace.router_provider by process() before this step), do
        # NOT let the auto-router overwrite it. The user's choice wins.
        # Previously this step called router.select_provider() and
        # overwrote both the trace and (implicitly) confused the
        # observatory into reporting a provider the runtime never used.
        if not self._config.enable_router:
            return message
        start = time.perf_counter()
        try:
            # If the user already picked a provider, keep it and skip
            # the auto-router entirely. The trace already reflects the
            # user's choice (set in process()).
            if trace.router_provider and trace.router_strategy == "user-selected":
                logger.info(
                    "Router step: skipping auto-selection — user explicitly "
                    "selected %s",
                    trace.router_provider,
                )
                trace.router_active = True
                enhanced = f"[Provider: {trace.router_provider}] {message}"
            else:
                router = self._get_router()
                provider = router.select_provider()
                trace.router_provider = provider
                trace.router_strategy = "auto"
                trace.router_active = True
                enhanced = f"[Provider: {provider}] {message}"
        except Exception as exc:
            logger.warning("Router step failed: %s", exc)
            trace.errors.append(f"router: {exc}")
            enhanced = message
        trace.router_latency_ms = (time.perf_counter() - start) * 1000
        return enhanced

    async def _step_memory(self, message: str, session_id: str, trace: PipelineTrace) -> list[str]:
        if not self._config.enable_memory:
            return []
        start = time.perf_counter()
        memory_context: list[str] = []
        try:
            memory = self._get_memory()
            memory.store(content=message, importance=0.5, metadata={"session_id": session_id, "type": "user_request"}, add_to_working=self._config.memory_add_to_working)
            relevant = memory.retrieve_relevant(count=self._config.memory_max_context_items, query=message)
            memory_context = [str(m.content) for m in relevant]
            trace.memory_items_retrieved = len(memory_context)
            trace.memory_working_size = len(memory.working_memory)
            trace.memory_active = True
        except Exception as exc:
            logger.warning("Memory step failed: %s", exc)
            trace.errors.append(f"memory: {exc}")
        trace.memory_latency_ms = (time.perf_counter() - start) * 1000
        return memory_context

    async def _step_context(self, message: str, session_id: str, memory_context: list[str], trace: PipelineTrace) -> str:
        if not self._config.enable_context:
            return message
        start = time.perf_counter()
        try:
            ctx_engine = self._get_context_engine()
            for mem in memory_context:
                ctx_engine.add(mem, source="memory")
            window = ctx_engine.build_with_sources(system="You are Agent-Reach, an intelligent AI operating system.", memories=memory_context, conversation=[{"role": "user", "content": message}], query=message)
            trace.context_tokens_used = window.total_tokens
            trace.context_budget = window.budget
            trace.context_active = True
            if window.items:
                return window.to_text()
        except Exception as exc:
            logger.warning("Context step failed: %s", exc)
            trace.errors.append(f"context: {exc}")
        trace.context_latency_ms = (time.perf_counter() - start) * 1000
        return message

    async def _step_moa(self, message: str, trace: PipelineTrace) -> tuple[str, dict[str, Any]]:
        if not self._config.enable_moa or len(message) < 100:
            return message, {}
        start = time.perf_counter()
        trace.moa_active = True
        trace.moa_mode = "available"
        trace.moa_providers = 1
        trace.moa_latency_ms = (time.perf_counter() - start) * 1000
        return message, {"moa_available": True}

    async def _step_reflection(self, outcome: TaskExecutionOutcome, message: str, trace: PipelineTrace) -> TaskExecutionOutcome:
        if not self._config.enable_reflection:
            return outcome
        start = time.perf_counter()
        try:
            reflection = self._get_reflection()
            from evaluation.engine import EvaluationReport, EvaluationResult
            results = []
            for r in outcome.results:
                passed = r.status == TaskStatus.SUCCEEDED
                score = 0.9 if passed else 0.2
                results.append(EvaluationResult(criterion_name=f"agent_{r.agent_type.value}", score=score, passed=passed))
            report = EvaluationReport(results=results)
            v2_report = reflection.reflect(report)
            trace.reflection_score = v2_report.reflection_score
            trace.reflection_insights = len(v2_report.insights)
            trace.reflection_active = True
            if self._config.reflection_auto_retry and v2_report.should_auto_retry:
                for _ in range(self._config.reflection_max_retries):
                    retry_outcome = await self._controller.handle_request(f"[RETRY] {message}")
                    if retry_outcome.status == TaskStatus.SUCCEEDED:
                        outcome = retry_outcome
                        trace.reflection_retried = True
                        break
        except Exception as exc:
            logger.warning("Reflection step failed: %s", exc)
            trace.errors.append(f"reflection: {exc}")
        trace.reflection_latency_ms = (time.perf_counter() - start) * 1000
        return outcome

    async def _step_knowledge_graph(self, outcome: TaskExecutionOutcome, trace: PipelineTrace) -> None:
        if not self._config.enable_knowledge_graph:
            return
        start = time.perf_counter()
        try:
            kg = self._get_knowledge_graph()
            from knowledge.graph import NodeType, EdgeType
            exec_id = kg.add_node(NodeType.EXECUTION, f"exec_{trace.request_id[:8]}", f"Execution of plan {outcome.plan.id}")
            for result in outcome.results:
                agent_id = kg.add_node(NodeType.AGENT, f"agent_{result.agent_type.value}", str(result.output)[:200])
                kg.add_edge(exec_id, agent_id, EdgeType.GENERATED_BY)
                trace.kg_edges_added += 1
            trace.kg_nodes_added = 1 + len(outcome.results)
            trace.kg_active = True
            # M9.18: evolve the graph from this execution's real text —
            # entity discovery, reinforcement, and provenance links.
            evolution = self._get_knowledge_evolution()
            if evolution is not None:
                text = " ".join(
                    str(r.output) for r in outcome.results if r.output
                )[:10_000]
                observation = evolution.observe_execution(
                    text, request_id=trace.request_id, execution_node_id=exec_id
                )
                trace.kg_nodes_added += len(observation.entities_discovered)
                trace.kg_edges_added += observation.relationships_added
        except Exception as exc:
            logger.warning("Knowledge graph step failed: %s", exc)
            trace.errors.append(f"knowledge_graph: {exc}")
        trace.kg_latency_ms = (time.perf_counter() - start) * 1000

    async def _step_learning(self, outcome: TaskExecutionOutcome, message: str, trace: PipelineTrace) -> None:
        if not self._config.enable_learning:
            return
        start = time.perf_counter()
        try:
            learning = self._get_learning()
            success = outcome.status == TaskStatus.SUCCEEDED
            quality = 1.0 if success else 0.3
            learning.record(task=message, provider=trace.router_provider or "default", mode=trace.moa_mode or "standard", quality=quality, latency_ms=trace.total_latency_ms, success=success, metadata={"request_id": trace.request_id, "plan_id": outcome.plan.id, "reflection_score": trace.reflection_score})
            trace.learning_recorded = True
            trace.learning_active = True
        except Exception as exc:
            logger.warning("Learning step failed: %s", exc)
            trace.errors.append(f"learning: {exc}")
        trace.learning_latency_ms = (time.perf_counter() - start) * 1000

    async def _step_tutti(self, outcome: TaskExecutionOutcome, message: str, session_id: str, trace: PipelineTrace) -> Optional[dict[str, Any]]:
        if not self._config.enable_tutti:
            return None
        start = time.perf_counter()
        try:
            tutti = self._get_tutti()
            from tutti.exporter import TargetPlatform
            ctx = tutti.export_context(target=TargetPlatform.AGENT_REACH, system_prompt="Agent-Reach intelligent session", conversation=[{"role": "user", "content": message}, {"role": "assistant", "content": outcome.answer}], metadata={"session_id": session_id, "plan_id": outcome.plan.id, "status": outcome.status.value, "request_id": trace.request_id})
            trace.tutti_export_id = ctx.id
            trace.tutti_active = True
            trace.tutti_latency_ms = (time.perf_counter() - start) * 1000
            return ctx.to_dict()
        except Exception as exc:
            logger.warning("Tutti step failed: %s", exc)
            trace.errors.append(f"tutti: {exc}")
        trace.tutti_latency_ms = (time.perf_counter() - start) * 1000
        return None

    # ── Lazy init ───────────────────────────────────────────────

    def _get_router(self) -> Any:
        if self._router is None:
            from routing.router import ReachIntelligenceRouter
            self._router = ReachIntelligenceRouter()
        return self._router

    def _get_memory(self) -> Any:
        if self._memory is None:
            from memory.longcat import LongCatMemoryEngine
            self._memory = LongCatMemoryEngine()
        return self._memory

    def _get_context_engine(self) -> Any:
        if self._context_engine is None:
            from context.engine import ContextEngine
            self._context_engine = ContextEngine()
        return self._context_engine

    def _get_moa(self) -> Any:
        if self._moa is None:
            from moa.engine import MOAEngine
            self._moa = MOAEngine()
        return self._moa

    def _get_reflection(self) -> Any:
        if self._reflection is None:
            from reflection.v2_engine import ReflectionEngineV2
            self._reflection = ReflectionEngineV2()
        return self._reflection

    def _get_knowledge_graph(self) -> Any:
        if self._knowledge_graph is None:
            from knowledge.graph import KnowledgeGraph
            self._knowledge_graph = KnowledgeGraph()
        return self._knowledge_graph

    def _get_learning(self) -> Any:
        if self._learning is None:
            from learning.engine import ReachLearningEngine
            self._learning = ReachLearningEngine()
        return self._learning

    def _get_knowledge_evolution(self) -> Any:
        """M9.18: evolution engine over the SHARED knowledge graph.

        Lazy like every other subsystem accessor; returns None only
        if construction fails (evolution then simply doesn't run —
        the base KG step is unaffected).
        """
        if not hasattr(self, "_knowledge_evolution"):
            try:
                from knowledge.evolution import KnowledgeEvolutionEngine

                self._knowledge_evolution = KnowledgeEvolutionEngine(
                    self._get_knowledge_graph()
                )
            except Exception:  # noqa: BLE001 — optional enhancement
                self._knowledge_evolution = None
        return self._knowledge_evolution

    def _get_tutti(self) -> Any:
        if self._tutti is None:
            from tutti.exporter import TuttiExporter
            self._tutti = TuttiExporter()
        return self._tutti

    # ── Subsystem extension point (M9.26) ───────────────────────

    def use_subsystem(self, name: str, implementation: Any) -> None:
        """Swap a pipeline subsystem for an alternative implementation.

        The M9.26 Future AI Layer's activation hook: callers (the
        AdapterRegistry, tests, the composition root) can bind an
        alternative memory / context / router implementation without
        modifying pipeline code. Validation of the implementation's
        interface is the caller's responsibility (AdapterRegistry
        validates structurally before ever calling this).
        """
        slots = {
            "memory": "_memory",
            "context": "_context_engine",
            "router": "_router",
            "moa": "_moa",
            "reflection": "_reflection",
            "knowledge_graph": "_knowledge_graph",
            "learning": "_learning",
            "tutti": "_tutti",
        }
        slot = slots.get(name)
        if slot is None:
            raise ValueError(
                f"Unknown subsystem '{name}'. Valid: {sorted(slots)}"
            )
        setattr(self, slot, implementation)

    # ── Trace access (M9.3) ─────────────────────────────────────

    @property
    def trace_store(self) -> "PipelineTraceStore":
        """The store holding every recorded execution trace."""
        return self._trace_store

    def get_trace(self, request_id: str) -> Optional[PipelineTrace]:
        """Look up a persisted execution trace by request id."""
        return self._trace_store.get(request_id)

    def list_traces(self, limit: int = 50) -> list[PipelineTrace]:
        """Return recent execution traces, newest first."""
        return self._trace_store.list_recent(limit)

    # ── Verify & Stats ──────────────────────────────────────────

    def verify_integration(self) -> dict[str, Any]:
        """Verify all subsystems are integrated and functional."""
        subsystems: dict[str, dict[str, Any]] = {}
        try:
            r = self._get_router()
            subsystems["router"] = {"active": self._config.enable_router, "type": type(r).__name__, "providers": r.list_providers()}
        except Exception as e:
            subsystems["router"] = {"active": False, "error": str(e)}
        try:
            m = self._get_memory()
            subsystems["memory"] = {"active": self._config.enable_memory, "type": type(m).__name__, "stats": m.get_stats()}
        except Exception as e:
            subsystems["memory"] = {"active": False, "error": str(e)}
        try:
            c = self._get_context_engine()
            subsystems["context"] = {"active": self._config.enable_context, "type": type(c).__name__, "stats": c.get_stats()}
        except Exception as e:
            subsystems["context"] = {"active": False, "error": str(e)}
        try:
            moa = self._get_moa()
            subsystems["moa"] = {"active": self._config.enable_moa, "type": type(moa).__name__, "stats": moa.get_stats()}
        except Exception as e:
            subsystems["moa"] = {"active": False, "error": str(e)}
        try:
            ref = self._get_reflection()
            subsystems["reflection"] = {"active": self._config.enable_reflection, "type": type(ref).__name__, "stats": ref.get_stats()}
        except Exception as e:
            subsystems["reflection"] = {"active": False, "error": str(e)}
        try:
            kg = self._get_knowledge_graph()
            subsystems["knowledge_graph"] = {"active": self._config.enable_knowledge_graph, "type": type(kg).__name__, "stats": kg.get_stats()}
        except Exception as e:
            subsystems["knowledge_graph"] = {"active": False, "error": str(e)}
        try:
            le = self._get_learning()
            subsystems["learning"] = {"active": self._config.enable_learning, "type": type(le).__name__, "stats": le.get_stats()}
        except Exception as e:
            subsystems["learning"] = {"active": False, "error": str(e)}
        try:
            t = self._get_tutti()
            subsystems["tutti"] = {"active": self._config.enable_tutti, "type": type(t).__name__, "exports": len(t.list_exports())}
        except Exception as e:
            subsystems["tutti"] = {"active": False, "error": str(e)}
        subsystems["pipeline"] = {"total_requests": self._total_requests, "avg_latency_ms": self._total_latency_ms / max(1, self._total_requests)}
        active_count = sum(1 for s in subsystems.values() if isinstance(s, dict) and s.get("active") is True)
        return {"subsystems": subsystems, "active_count": active_count, "total_subsystems": len(subsystems) - 1, "all_active": active_count >= 8}

    def get_stats(self) -> dict[str, Any]:
        return {"total_requests": self._total_requests, "avg_latency_ms": self._total_latency_ms / max(1, self._total_requests), "config": {"router": self._config.enable_router, "memory": self._config.enable_memory, "context": self._config.enable_context, "moa": self._config.enable_moa, "reflection": self._config.enable_reflection, "knowledge_graph": self._config.enable_knowledge_graph, "learning": self._config.enable_learning, "tutti": self._config.enable_tutti}}

    def clear(self) -> None:
        if self._memory:
            self._memory.clear()
        if self._context_engine:
            self._context_engine.clear()
        if self._knowledge_graph:
            self._knowledge_graph.clear()
        if self._learning:
            self._learning.clear()
        if self._tutti:
            self._tutti.clear()
        self._trace_store.clear()
        self._total_requests = 0
        self._total_latency_ms = 0.0


# ---------------------------------------------------------------------------
# Provider name normalization (M9 fix)
# ---------------------------------------------------------------------------

# Same mapping as conversation/engine.py's _FRONTEND_TO_RUNTIME_PROVIDER.
# Duplicated rather than imported to keep core/ from depending on
# conversation/ (core is the inner layer; conversation wraps it). The
# mapping is tiny and unlikely to change often.
_FRONTEND_TO_RUNTIME_PROVIDER: dict[str, str] = {
    "google": "gemini",
}


def _to_runtime_provider_name(frontend_name: str) -> str:
    """Map a frontend/API provider id to the runtime ProviderManager id.

    Returns the input unchanged when no mapping exists — the caller
    (set_provider) will raise ConfigurationError if the runtime doesn't
    support it, which we catch and log as a warning.
    """
    if not frontend_name:
        return frontend_name
    return _FRONTEND_TO_RUNTIME_PROVIDER.get(frontend_name, frontend_name)
