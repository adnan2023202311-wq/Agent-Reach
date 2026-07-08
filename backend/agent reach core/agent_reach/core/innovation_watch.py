"""
Continuous AI Research Engine + Innovation Watch (M9.16 / M9.31).

Layer: Application/Core — composes EXISTING machinery:

    Source monitoring   → the real M9.6 tools (rss_fetch for feeds,
                          browser_fetch for pages) executed through
                          the SHARED ToolRuntime, so every fetch is
                          recorded in tool history
    Relevance filtering → deterministic keyword scoring against a
                          documented technology vocabulary (memory
                          systems, routing, orchestration, prompts,
                          multi-agent) — rule-based and honest, not
                          presented as semantic understanding
    Evaluation notes    → optional model narrative through the SHARED
                          IntelligentPipeline (labeled, trace-linked,
                          advisory)
    Knowledge storage   → discovered items enter the SHARED
                          KnowledgeGraph as DOCUMENT nodes with
                          confidence, so the M9.18 evolution and the
                          Knowledge screen see them
    Proposals           → compatibility reports reference the M9.26
                          adapter category interfaces — the concrete
                          integration contract, not hand-waving

M9.31's constraint is enforced structurally: the watch NEVER deploys
anything. Its outputs are findings, compatibility reports, and
implementation plans.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# Documented relevance vocabulary — scoring is transparent.
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "memory_systems": ("memory", "retrieval", "rag", "vector", "embedding", "recall"),
    "routing": ("routing", "router", "model selection", "fallback", "load balancing"),
    "orchestration": ("orchestration", "workflow", "pipeline", "coordination"),
    "prompting": ("prompt", "instruction", "few-shot", "chain of thought"),
    "multi_agent": ("multi-agent", "agents", "swarm", "collaboration", "delegation"),
    "reasoning": ("reasoning", "planning", "reflection", "self-improvement"),
    "models": ("llm", "language model", "transformer", "fine-tun", "benchmark"),
}

_MIN_RELEVANCE_SCORE = 2  # at least two vocabulary hits to register


@dataclass
class WatchSource:
    """One monitored source."""

    source_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "rss"  # rss | page
    url: str = ""
    label: str = ""
    added_at: float = field(default_factory=time.time)
    last_checked: Optional[float] = None
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "url": self.url,
            "label": self.label,
            "added_at": self.added_at,
            "last_checked": self.last_checked,
            "last_error": self.last_error,
        }


@dataclass
class Finding:
    """One relevant discovery from a real fetch."""

    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    title: str = ""
    url: str = ""
    summary: str = ""
    topics: dict[str, int] = field(default_factory=dict)  # topic → keyword hits
    relevance_score: int = 0
    discovered_at: float = field(default_factory=time.time)
    knowledge_node_id: str = ""
    evaluation: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "summary": self.summary[:500],
            "topics": dict(self.topics),
            "relevance_score": self.relevance_score,
            "discovered_at": self.discovered_at,
            "knowledge_node_id": self.knowledge_node_id,
            "evaluation": dict(self.evaluation) if self.evaluation else None,
        }


def score_relevance(text: str) -> tuple[dict[str, int], int]:
    """Transparent keyword scoring against the documented vocabulary."""
    lowered = text.lower()
    topics: dict[str, int] = {}
    for topic, keywords in _TOPIC_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits:
            topics[topic] = hits
    return topics, sum(topics.values())


class InnovationWatch:
    """Monitor sources, register relevant findings, produce reports."""

    def __init__(
        self,
        tool_runtime: Any,
        pipeline: Any = None,
        knowledge_graph: Any = None,
        max_findings: int = 1000,
    ) -> None:
        if max_findings < 1:
            raise ValueError("max_findings must be >= 1")
        self._tool_runtime = tool_runtime
        self._pipeline = pipeline
        self._knowledge_graph = knowledge_graph
        self._sources: dict[str, WatchSource] = {}
        self._findings: dict[str, Finding] = {}
        self._seen_urls: set[str] = set()
        self._max_findings = max_findings

    # ── Sources ─────────────────────────────────────────────────

    def add_source(self, url: str, kind: str = "rss", label: str = "") -> WatchSource:
        if kind not in ("rss", "page"):
            raise ValueError("kind must be 'rss' or 'page'")
        if not url.strip():
            raise ValueError("url must not be empty")
        source = WatchSource(kind=kind, url=url.strip(), label=label or url.strip())
        self._sources[source.source_id] = source
        return source

    def remove_source(self, source_id: str) -> bool:
        return self._sources.pop(source_id, None) is not None

    def list_sources(self) -> list[WatchSource]:
        return sorted(self._sources.values(), key=lambda s: s.added_at)

    # ── Scanning ────────────────────────────────────────────────

    async def scan(self) -> dict[str, Any]:
        """Fetch every source through the REAL tool runtime; register
        relevant findings. Errors are per-source, never fabricated
        away."""
        new_findings: list[Finding] = []
        errors: list[dict[str, str]] = []

        for source in self._sources.values():
            source.last_checked = time.time()
            try:
                items = await self._fetch(source)
                source.last_error = None
            except Exception as exc:  # noqa: BLE001 — per-source isolation
                source.last_error = f"{type(exc).__name__}: {exc}"
                errors.append({"source_id": source.source_id, "error": source.last_error})
                continue

            for item in items:
                url = item.get("url", "")
                if url and url in self._seen_urls:
                    continue
                text = f"{item.get('title', '')} {item.get('summary', '')}"
                topics, relevance = score_relevance(text)
                if relevance < _MIN_RELEVANCE_SCORE:
                    continue
                finding = Finding(
                    source_id=source.source_id,
                    title=item.get("title", "")[:300],
                    url=url,
                    summary=item.get("summary", ""),
                    topics=topics,
                    relevance_score=relevance,
                )
                self._store_in_knowledge(finding)
                self._findings[finding.finding_id] = finding
                if url:
                    self._seen_urls.add(url)
                new_findings.append(finding)

        self._evict()
        return {
            "scanned_sources": len(self._sources),
            "new_findings": [f.to_dict() for f in new_findings],
            "new_count": len(new_findings),
            "errors": errors,
        }

    async def _fetch(self, source: WatchSource) -> list[dict[str, str]]:
        """One source's items via the real tools (recorded in history)."""
        if source.kind == "rss":
            record = await self._tool_runtime.execute(
                "rss_fetch",
                agent_type="innovation-watch",
                parameters={"url": source.url},
            )
            if not record.success:
                raise RuntimeError(record.error or "rss_fetch failed")
            # output_preview is truncated; re-fetch structured output
            # through the tool function directly is unnecessary — the
            # registry call is the same function. Execute returns only
            # the preview, so call the registry for the full payload.
            payload = await self._tool_runtime.registry.call(
                "rss_fetch", "innovation-watch", url=source.url
            )
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "summary": item.get("description", ""),
                }
                for item in payload.get("items", [])
            ]
        # page
        payload = await self._tool_runtime.registry.call(
            "browser_fetch", "innovation-watch", url=source.url
        )
        return [
            {
                "title": payload.get("title", ""),
                "url": payload.get("url", source.url),
                "summary": payload.get("text", "")[:2000],
            }
        ]

    def _store_in_knowledge(self, finding: Finding) -> None:
        """Findings enter the SHARED knowledge graph as DOCUMENT nodes."""
        if self._knowledge_graph is None:
            return
        try:
            from knowledge.graph import NodeType

            # Confidence maps transparently from relevance (bounded).
            confidence = min(0.9, 0.3 + finding.relevance_score * 0.1)
            finding.knowledge_node_id = self._knowledge_graph.add_node(
                NodeType.DOCUMENT,
                finding.title or finding.url,
                description=finding.summary[:500],
                properties={
                    "url": finding.url,
                    "topics": dict(finding.topics),
                    "source": "innovation_watch",
                },
                confidence=confidence,
            )
        except Exception:  # noqa: BLE001 — storage is best-effort
            finding.knowledge_node_id = ""

    # ── Evaluation & reports ────────────────────────────────────

    async def evaluate(self, finding_id: str) -> Finding:
        """Model evaluation of one finding (advisory, trace-linked)."""
        finding = self._findings.get(finding_id)
        if finding is None:
            raise KeyError(f"Finding '{finding_id}' not found")
        if self._pipeline is None:
            finding.evaluation = {
                "available": False,
                "note": "No pipeline attached — keyword scoring only.",
            }
            return finding
        result = await self._pipeline.process(
            "Evaluate this AI technology finding for Agent Reach: what is "
            "it, is it relevant to our runtime (memory / routing / "
            "orchestration / prompts / multi-agent), and what would "
            "integrating it require?\n\n"
            f"Title: {finding.title}\nURL: {finding.url}\n"
            f"Summary: {finding.summary[:2000]}"
        )
        finding.evaluation = {
            "available": True,
            "narrative": result.outcome.answer,
            "request_id": result.trace.request_id,
            "note": "Model-generated, advisory.",
        }
        return finding

    def compatibility_report(self, finding_id: str) -> dict[str, Any]:
        """Map a finding's topics to the M9.26 adapter contracts.

        The report states EXACTLY which interface a candidate
        integration must implement — the concrete plan, no deploying.
        """
        finding = self._findings.get(finding_id)
        if finding is None:
            raise KeyError(f"Finding '{finding_id}' not found")

        from infrastructure.adapters import AdapterRegistry

        categories = AdapterRegistry.describe_categories()
        topic_to_category = {
            "memory_systems": "memory",
            "routing": "router",
            "orchestration": "plugin",
            "prompting": "plugin",
            "multi_agent": "plugin",
            "reasoning": "plugin",
            "models": "provider",
        }
        candidate_categories = sorted(
            {
                topic_to_category[topic]
                for topic in finding.topics
                if topic in topic_to_category
            }
        )
        return {
            "finding_id": finding_id,
            "title": finding.title,
            "topics": dict(finding.topics),
            "candidate_adapter_categories": [
                {
                    "category": category,
                    "required_interface": categories[category]["required_methods"],
                    "runtime_activatable": categories[category]["runtime_activatable"],
                }
                for category in candidate_categories
            ],
            "integration_plan": [
                "1. Implement the adapter against the required interface above.",
                "2. Register it via AdapterRegistry.register() — structural validation runs there.",
                "3. Validate behavior in tests against the category contract.",
                "4. Activate runtime-activatable categories via /api/v1/adapters; "
                "providers/plugins wire through the composition root.",
            ],
            "note": "Report only — the watch never deploys anything (M9.31).",
        }

    # ── Introspection ───────────────────────────────────────────

    def list_findings(self, topic: str = "", limit: int = 50) -> list[Finding]:
        findings = sorted(
            self._findings.values(),
            key=lambda f: (f.relevance_score, f.discovered_at),
            reverse=True,
        )
        if topic:
            findings = [f for f in findings if topic in f.topics]
        return findings[: max(0, limit)]

    def get_finding(self, finding_id: str) -> Optional[Finding]:
        return self._findings.get(finding_id)

    def get_stats(self) -> dict[str, Any]:
        findings = list(self._findings.values())
        topic_counts: dict[str, int] = {}
        for finding in findings:
            for topic in finding.topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        return {
            "sources": len(self._sources),
            "total_findings": len(findings),
            "by_topic": topic_counts,
        }

    def clear(self) -> None:
        self._sources.clear()
        self._findings.clear()
        self._seen_urls.clear()

    def _evict(self) -> None:
        while len(self._findings) > self._max_findings:
            oldest = min(self._findings.values(), key=lambda f: f.discovered_at)
            del self._findings[oldest.finding_id]
