"""
Prompt Evolution Engine (M9.20).

Layer: Application — composes the EXISTING PromptIntelligence (M7)
and its PromptLibrary. No parallel prompt store.

M9.20 requirements and how they map onto existing machinery:

- "Continuously improve prompts using historical executions,
  performance metrics, user feedback"
      → evolution proposals are derived from PromptIntelligence's
        REAL learning entries (record_usage data: quality ratings,
        latency, providers) and the library's structural analysis
        (suggest_optimizations).
- "Maintain prompt version history and rollback support"
      → the engine snapshots every template revision it makes (and
        the pre-existing state before its first change), exposing
        get_history() and rollback(). The library's own monotonic
        version counter remains the single version authority.

Honesty contract: proposals state the evidence they are based on.
When a prompt has no usage data, the engine says so — it does not
invent quality numbers. Template rewriting is intentionally
conservative and rule-based (structure, not semantics): semantic
rewriting requires a model call, which callers can do through the
pipeline and then register via propose_external().
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from prompts.intelligence import PromptIntelligence


# Evidence thresholds — a proposal needs real data behind it.
_MIN_USES_FOR_QUALITY_EVOLUTION = 5
_LOW_QUALITY_THRESHOLD = 0.5


@dataclass
class PromptVersionSnapshot:
    """One recorded prompt revision."""

    version: int
    template: str
    recorded_at: float = field(default_factory=time.time)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "template": self.template,
            "recorded_at": self.recorded_at,
            "reason": self.reason,
        }


@dataclass
class EvolutionProposal:
    """A proposed prompt improvement with its evidence."""

    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_name: str = ""
    current_version: int = 0
    proposed_template: str = ""
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    source: str = "rule_based"  # rule_based | external
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "prompt_name": self.prompt_name,
            "current_version": self.current_version,
            "proposed_template": self.proposed_template,
            "rationale": self.rationale,
            "evidence": dict(self.evidence),
            "source": self.source,
            "created_at": self.created_at,
        }


class PromptEvolutionEngine:
    """Evolve prompts from real usage data, with history and rollback."""

    def __init__(self, intelligence: Optional[PromptIntelligence] = None) -> None:
        self._intelligence = intelligence or PromptIntelligence()
        self._history: dict[str, list[PromptVersionSnapshot]] = {}
        self._proposals: dict[str, EvolutionProposal] = {}

    @property
    def intelligence(self) -> PromptIntelligence:
        return self._intelligence

    @property
    def library(self):
        return self._intelligence.library

    # ── Analysis & proposals ────────────────────────────────────

    def analyze(self, prompt_name: str) -> dict[str, Any]:
        """Real usage + structural analysis for one prompt."""
        prompt = self.library.get(prompt_name)
        if prompt is None:
            raise KeyError(f"Prompt '{prompt_name}' not found")
        learning = self._intelligence.get_learning_stats(prompt_name)
        return {
            "prompt_name": prompt_name,
            "version": prompt.version,
            "template_length": len(prompt.template),
            "variables": list(prompt.variables),
            "usage": learning,
            "structural_suggestions": self._intelligence.suggest_optimizations(
                prompt_name
            ),
            "has_sufficient_data": learning.get("total_uses", 0)
            >= _MIN_USES_FOR_QUALITY_EVOLUTION,
        }

    def propose(self, prompt_name: str) -> list[EvolutionProposal]:
        """Generate evolution proposals from real evidence.

        Rule-based structural improvements are proposed whenever the
        structure warrants them; quality-driven proposals require
        enough real usage data. No data → no invented proposals.
        """
        prompt = self.library.get(prompt_name)
        if prompt is None:
            raise KeyError(f"Prompt '{prompt_name}' not found")

        proposals: list[EvolutionProposal] = []
        learning = self._intelligence.get_learning_stats(prompt_name)
        total_uses = learning.get("total_uses", 0)

        # Structural: overly long template → propose trimmed whitespace
        # (conservative, reversible, purely structural).
        stripped = "\n".join(
            line.rstrip() for line in prompt.template.splitlines()
        ).strip()
        if stripped != prompt.template:
            proposals.append(
                self._register_proposal(
                    EvolutionProposal(
                        prompt_name=prompt_name,
                        current_version=prompt.version,
                        proposed_template=stripped,
                        rationale="Normalize whitespace (trailing spaces / padding) — structural cleanup.",
                        evidence={"original_length": len(prompt.template), "new_length": len(stripped)},
                    )
                )
            )

        # Quality-driven: only with sufficient real usage.
        if total_uses >= _MIN_USES_FOR_QUALITY_EVOLUTION:
            avg_quality = learning.get("avg_quality", 0.0)
            if avg_quality < _LOW_QUALITY_THRESHOLD:
                improved = self._add_clarity_scaffold(prompt.template)
                if improved != prompt.template:
                    proposals.append(
                        self._register_proposal(
                            EvolutionProposal(
                                prompt_name=prompt_name,
                                current_version=prompt.version,
                                proposed_template=improved,
                                rationale=(
                                    f"Average output quality is {avg_quality:.2f} over "
                                    f"{total_uses} real uses — add explicit task/output "
                                    "structure to reduce ambiguity."
                                ),
                                evidence={
                                    "avg_quality": avg_quality,
                                    "total_uses": total_uses,
                                    "avg_latency_ms": learning.get("avg_latency_ms", 0.0),
                                },
                            )
                        )
                    )
        return proposals

    def propose_external(
        self,
        prompt_name: str,
        proposed_template: str,
        rationale: str,
        evidence: Optional[dict[str, Any]] = None,
    ) -> EvolutionProposal:
        """Register an externally generated proposal (e.g. produced by
        a model call through the pipeline, or human feedback)."""
        prompt = self.library.get(prompt_name)
        if prompt is None:
            raise KeyError(f"Prompt '{prompt_name}' not found")
        if not proposed_template.strip():
            raise ValueError("proposed_template must not be empty")
        return self._register_proposal(
            EvolutionProposal(
                prompt_name=prompt_name,
                current_version=prompt.version,
                proposed_template=proposed_template,
                rationale=rationale,
                evidence=dict(evidence or {}),
                source="external",
            )
        )

    # ── Application, history & rollback ─────────────────────────

    def apply_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Apply a proposal: snapshot the current version, then
        register the new template (library bumps the version)."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"Proposal '{proposal_id}' not found")
        prompt = self.library.get(proposal.prompt_name)
        if prompt is None:
            raise KeyError(f"Prompt '{proposal.prompt_name}' no longer exists")

        self._snapshot(prompt.name, prompt.version, prompt.template,
                       reason=f"before proposal {proposal.proposal_id}")
        updated = self.library.register(
            prompt.name,
            proposal.proposed_template,
            description=prompt.description,
            tags=prompt.tags,
            owner=prompt.owner,
            metadata=prompt.metadata,
        )
        self._snapshot(prompt.name, updated.version, updated.template,
                       reason=f"applied proposal {proposal.proposal_id}: {proposal.rationale}")
        del self._proposals[proposal_id]
        return {
            "prompt_name": prompt.name,
            "previous_version": proposal.current_version,
            "new_version": updated.version,
            "applied_proposal": proposal.to_dict(),
        }

    def get_history(self, prompt_name: str) -> list[PromptVersionSnapshot]:
        """Recorded revisions for a prompt, oldest first."""
        return list(self._history.get(prompt_name, []))

    def rollback(self, prompt_name: str, version: int) -> dict[str, Any]:
        """Restore a prompt to a recorded version's template.

        The restore itself is registered as a NEW version (the library
        counter stays monotonic) — history is never rewritten.
        """
        snapshots = self._history.get(prompt_name, [])
        target = next((s for s in snapshots if s.version == version), None)
        if target is None:
            raise KeyError(
                f"No recorded snapshot of '{prompt_name}' at version {version}"
            )
        prompt = self.library.get(prompt_name)
        if prompt is None:
            raise KeyError(f"Prompt '{prompt_name}' not found")

        self._snapshot(prompt_name, prompt.version, prompt.template,
                       reason=f"before rollback to v{version}")
        updated = self.library.register(
            prompt_name,
            target.template,
            description=prompt.description,
            tags=prompt.tags,
            owner=prompt.owner,
            metadata=prompt.metadata,
        )
        self._snapshot(prompt_name, updated.version, updated.template,
                       reason=f"rollback to v{version}")
        return {
            "prompt_name": prompt_name,
            "restored_from_version": version,
            "new_version": updated.version,
        }

    def list_proposals(self, prompt_name: str = "") -> list[EvolutionProposal]:
        proposals = list(self._proposals.values())
        if prompt_name:
            proposals = [p for p in proposals if p.prompt_name == prompt_name]
        return sorted(proposals, key=lambda p: p.created_at)

    def clear(self) -> None:
        self._history.clear()
        self._proposals.clear()

    # ── Internals ───────────────────────────────────────────────

    def _register_proposal(self, proposal: EvolutionProposal) -> EvolutionProposal:
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def _snapshot(
        self, prompt_name: str, version: int, template: str, reason: str
    ) -> None:
        history = self._history.setdefault(prompt_name, [])
        # Don't duplicate an identical (version, template) snapshot.
        if any(s.version == version and s.template == template for s in history):
            return
        history.append(
            PromptVersionSnapshot(version=version, template=template, reason=reason)
        )

    @staticmethod
    def _add_clarity_scaffold(template: str) -> str:
        """Conservative structural improvement: explicit sections.

        Purely additive scaffolding — the original content is kept
        verbatim as the task body.
        """
        if "## Task" in template or "## Output" in template:
            return template  # already structured
        return (
            "## Task\n"
            f"{template.strip()}\n\n"
            "## Output requirements\n"
            "- Be specific and complete.\n"
            "- State assumptions explicitly.\n"
            "- If information is missing, say what is missing."
        )
