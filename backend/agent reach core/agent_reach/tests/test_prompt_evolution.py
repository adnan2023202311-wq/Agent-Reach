"""Tests for M9.20 — Prompt Evolution Engine.

Proves: evidence-gated proposals (no invented findings without real
usage data), conservative structural rewrites, external proposal
registration, apply with library-version bump, full version history,
and rollback that restores content as a NEW version (monotonic
history, never rewritten).
"""

from __future__ import annotations

import pytest

from prompts.evolution import PromptEvolutionEngine
from prompts.intelligence import PromptIntelligence


def _engine_with_prompt(
    name: str = "research", template: str = "Research {{topic}} thoroughly and report findings."
) -> PromptEvolutionEngine:
    engine = PromptEvolutionEngine(PromptIntelligence())
    engine.library.register(name, template, description="d", tags=["t"])
    return engine


def _record_uses(engine: PromptEvolutionEngine, name: str, count: int, quality: float) -> None:
    for i in range(count):
        engine.intelligence.record_usage(
            name,
            variables={"topic": f"topic {i}"},
            output_quality=quality,
            latency_ms=100.0,
            provider="anthropic",
        )


# ===========================================================================
# Analysis & proposals
# ===========================================================================


class TestAnalysis:
    def test_analyze_reports_real_usage(self) -> None:
        engine = _engine_with_prompt()
        _record_uses(engine, "research", 3, 0.8)
        analysis = engine.analyze("research")
        assert analysis["usage"]["total_uses"] == 3
        assert analysis["has_sufficient_data"] is False  # below 5

    def test_analyze_unknown_prompt_raises(self) -> None:
        engine = PromptEvolutionEngine()
        with pytest.raises(KeyError):
            engine.analyze("ghost")


class TestProposals:
    def test_no_usage_no_quality_proposals(self) -> None:
        """Quality-driven proposals require ≥5 real uses."""
        engine = _engine_with_prompt()
        proposals = engine.propose("research")
        assert all("quality" not in p.rationale.lower() for p in proposals)

    def test_low_quality_with_evidence_proposes_scaffold(self) -> None:
        engine = _engine_with_prompt()
        _record_uses(engine, "research", 6, quality=0.2)
        proposals = engine.propose("research")
        quality_props = [p for p in proposals if "quality" in p.rationale.lower()]
        assert len(quality_props) == 1
        prop = quality_props[0]
        assert prop.evidence["total_uses"] == 6
        assert prop.evidence["avg_quality"] == pytest.approx(0.2)
        assert "## Task" in prop.proposed_template
        # original content preserved verbatim
        assert "Research {{topic}} thoroughly" in prop.proposed_template

    def test_good_quality_no_scaffold_proposal(self) -> None:
        engine = _engine_with_prompt()
        _record_uses(engine, "research", 6, quality=0.9)
        proposals = engine.propose("research")
        assert all("## Task" not in p.proposed_template for p in proposals)

    def test_whitespace_normalization_proposal(self) -> None:
        engine = _engine_with_prompt(
            name="messy", template="Do the thing.   \n\n\n   "
        )
        proposals = engine.propose("messy")
        ws = [p for p in proposals if "whitespace" in p.rationale.lower()]
        assert len(ws) == 1
        assert ws[0].proposed_template == "Do the thing."

    def test_external_proposal_registration(self) -> None:
        engine = _engine_with_prompt()
        prop = engine.propose_external(
            "research",
            "Better template {{topic}}",
            rationale="Model-suggested rewrite",
            evidence={"model": "test"},
        )
        assert prop.source == "external"
        assert engine.list_proposals("research")[-1].proposal_id == prop.proposal_id

    def test_external_empty_template_rejected(self) -> None:
        engine = _engine_with_prompt()
        with pytest.raises(ValueError):
            engine.propose_external("research", "  ", rationale="x")

    def test_propose_unknown_prompt_raises(self) -> None:
        engine = PromptEvolutionEngine()
        with pytest.raises(KeyError):
            engine.propose("ghost")


# ===========================================================================
# Apply / history / rollback
# ===========================================================================


class TestApplyAndRollback:
    def test_apply_bumps_library_version_and_records_history(self) -> None:
        engine = _engine_with_prompt()
        prop = engine.propose_external(
            "research", "New template {{topic}}", rationale="upgrade"
        )
        result = engine.apply_proposal(prop.proposal_id)
        assert result["previous_version"] == 1
        assert result["new_version"] == 2
        assert engine.library.get("research").template == "New template {{topic}}"

        history = engine.get_history("research")
        versions = [s.version for s in history]
        assert 1 in versions and 2 in versions
        # proposal consumed
        assert engine.list_proposals("research") == []

    def test_apply_unknown_proposal_raises(self) -> None:
        engine = _engine_with_prompt()
        with pytest.raises(KeyError):
            engine.apply_proposal("ghost")

    def test_rollback_restores_as_new_version(self) -> None:
        engine = _engine_with_prompt(template="Original {{topic}}")
        prop = engine.propose_external("research", "Changed {{topic}}", rationale="r")
        engine.apply_proposal(prop.proposal_id)
        assert engine.library.get("research").version == 2

        result = engine.rollback("research", version=1)
        assert result["restored_from_version"] == 1
        assert result["new_version"] == 3  # monotonic — never rewound
        assert engine.library.get("research").template == "Original {{topic}}"
        # full audit trail retained
        assert len(engine.get_history("research")) >= 3

    def test_rollback_unknown_version_raises(self) -> None:
        engine = _engine_with_prompt()
        with pytest.raises(KeyError):
            engine.rollback("research", version=42)

    def test_intelligence_learning_survives_evolution(self) -> None:
        """Applying a proposal must not lose recorded usage data —
        the library register() path preserves prompt identity."""
        engine = _engine_with_prompt()
        _record_uses(engine, "research", 4, 0.7)
        prop = engine.propose_external("research", "V2 {{topic}}", rationale="r")
        engine.apply_proposal(prop.proposal_id)
        assert engine.intelligence.get_learning_stats("research")["total_uses"] == 4
