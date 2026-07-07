"""
Multi-Model Orchestration — MOA (M7.4).

Native multi-model execution with parallel, sequential, voting,
consensus, and judge-based strategies.

Features:
- Parallel Execution
- Sequential Execution
- Voting
- Consensus
- Judge Agent
- Critic Agent
- Synthesizer Agent
- Confidence Calculation
- Result Fusion
- Conflict Resolution
- Quality Ranking
- Retry Strategy
- Cost Optimization

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional


class MOAExecutionMode(str, Enum):
    """How multiple models are orchestrated."""
    PARALLEL = "parallel"        # Run all models concurrently
    SEQUENTIAL = "sequential"    # Run models one after another
    VOTING = "voting"            # Majority vote on the answer
    CONSENSUS = "consensus"      # All must agree
    JUDGE = "judge"              # One model judges outputs
    CRITIC = "critic"            # One model critiques, another improves
    SYNTHESIZE = "synthesize"    # Combine outputs into one


@dataclass
class MOAResult:
    """Result from a multi-model orchestration run.

    Attributes:
        mode: The execution mode used.
        provider_results: Individual provider responses.
        final_answer: The consolidated final answer.
        confidence: Estimated confidence (0.0-1.0).
        consensus: Whether all models agreed.
        voting_result: Voting tally {answer: count}.
        judge_feedback: Feedback from judge model.
        total_latency_ms: Total execution time.
        cost_estimate: Estimated cost.
        attempts: Number of retry attempts.
        metadata: Additional metadata.
    """

    mode: MOAExecutionMode = MOAExecutionMode.PARALLEL
    provider_results: dict[str, str] = field(default_factory=dict)
    final_answer: str = ""
    confidence: float = 0.0
    consensus: bool = False
    voting_result: dict[str, int] = field(default_factory=dict)
    judge_feedback: str = ""
    total_latency_ms: float = 0.0
    cost_estimate: float = 0.0
    attempts: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "provider_count": len(self.provider_results),
            "final_answer": self.final_answer,
            "confidence": self.confidence,
            "consensus": self.consensus,
            "voting_result": dict(self.voting_result),
            "judge_feedback": self.judge_feedback,
            "total_latency_ms": self.total_latency_ms,
            "cost_estimate": self.cost_estimate,
            "attempts": self.attempts,
            "metadata": dict(self.metadata),
        }


@dataclass
class MOAStrategy:
    """Configuration for a MOA execution strategy.

    Attributes:
        mode: Execution mode.
        providers: List of providers to use.
        max_retries: Max retries per provider.
        confidence_threshold: Minimum confidence to accept.
        require_consensus: Whether consensus is required.
        judge_provider: Provider used as judge (for JUDGE/CRITIC modes).
        cost_budget: Maximum cost budget.
    """

    mode: MOAExecutionMode = MOAExecutionMode.PARALLEL
    providers: list[str] = field(default_factory=list)
    max_retries: int = 2
    confidence_threshold: float = 0.6
    require_consensus: bool = False
    judge_provider: str = ""
    cost_budget: float = float("inf")


# Type alias for a model call function
ModelCallFunc = Callable[[str, str], Awaitable[str]]
"""A callable that takes (provider_name, prompt) and returns the response text."""


class MOAEngine:
    """Multi-Model Orchestration Engine.

    Coordinates multiple AI provider calls through different execution
    strategies and synthesizes results.
    """

    def __init__(
        self,
        model_caller: Optional[ModelCallFunc] = None,
    ) -> None:
        self._model_caller = model_caller
        self._execution_history: list[MOAResult] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        prompt: str,
        strategy: MOAStrategy,
        system: str = "",
    ) -> MOAResult:
        """Execute a prompt using the given MOA strategy.

        Args:
            prompt: The user prompt to send.
            strategy: MOA execution strategy.
            system: Optional system prompt.

        Returns:
            MOAResult with the consolidated answer.
        """
        start = time.perf_counter()

        if strategy.mode == MOAExecutionMode.PARALLEL:
            result = await self._execute_parallel(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.SEQUENTIAL:
            result = await self._execute_sequential(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.VOTING:
            result = await self._execute_voting(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.CONSENSUS:
            result = await self._execute_consensus(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.JUDGE:
            result = await self._execute_judge(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.CRITIC:
            result = await self._execute_critic(prompt, strategy, system)
        elif strategy.mode == MOAExecutionMode.SYNTHESIZE:
            result = await self._execute_synthesize(prompt, strategy, system)
        else:
            result = await self._execute_parallel(prompt, strategy, system)

        result.total_latency_ms = (time.perf_counter() - start) * 1000
        result.cost_estimate = self._estimate_cost(strategy)
        self._execution_history.append(result)
        return result

    # ------------------------------------------------------------------
    # Execution modes
    # ------------------------------------------------------------------

    async def _execute_parallel(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Run all providers in parallel and synthesize."""
        if not self._model_caller:
            return MOAResult(
                mode=MOAExecutionMode.PARALLEL,
                final_answer="No model caller configured.",
                confidence=0.0,
            )

        tasks = [
            self._call_with_retry(p, prompt, strategy.max_retries)
            for p in strategy.providers
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        provider_results: dict[str, str] = {}
        for provider, response in zip(strategy.providers, responses):
            if isinstance(response, Exception):
                provider_results[provider] = f"ERROR: {response}"
            else:
                provider_results[provider] = response

        final = self._synthesize(list(provider_results.values()))
        confidence = self._compute_confidence(list(provider_results.values()))

        return MOAResult(
            mode=MOAExecutionMode.PARALLEL,
            provider_results=provider_results,
            final_answer=final,
            confidence=confidence,
        )

    async def _execute_sequential(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Run providers sequentially, each building on the previous."""
        if not self._model_caller:
            return MOAResult(
                mode=MOAExecutionMode.SEQUENTIAL,
                final_answer="No model caller configured.",
            )

        provider_results: dict[str, str] = {}
        current_prompt = prompt

        for provider in strategy.providers:
            response = await self._call_with_retry(provider, current_prompt, strategy.max_retries)
            provider_results[provider] = response
            # Next provider gets the previous output as additional context
            current_prompt = f"{prompt}\n\nPrevious output: {response}"

        final = list(provider_results.values())[-1] if provider_results else ""
        return MOAResult(
            mode=MOAExecutionMode.SEQUENTIAL,
            provider_results=provider_results,
            final_answer=final,
            confidence=self._compute_confidence([final]),
        )

    async def _execute_voting(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Run providers in parallel, use majority vote."""
        if not self._model_caller:
            return MOAResult(mode=MOAExecutionMode.VOTING, final_answer="")

        tasks = [
            self._call_with_retry(p, prompt, strategy.max_retries)
            for p in strategy.providers
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        provider_results: dict[str, str] = {}
        answers: list[str] = []
        for provider, response in zip(strategy.providers, responses):
            text = str(response) if not isinstance(response, Exception) else ""
            provider_results[provider] = text
            if text:
                answers.append(text)

        # Simple majority vote on first sentence or whole answer
        tally = Counter(a[:100] for a in answers)
        winner = tally.most_common(1)[0][0] if tally else ""
        confidence = tally[winner] / max(1, len(answers)) if answers else 0.0

        return MOAResult(
            mode=MOAExecutionMode.VOTING,
            provider_results=provider_results,
            final_answer=winner,
            confidence=confidence,
            voting_result=dict(tally),
        )

    async def _execute_consensus(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Require all providers to agree. Retry until consensus."""
        if not self._model_caller:
            return MOAResult(mode=MOAExecutionMode.CONSENSUS, final_answer="")

        max_iterations = 3
        provider_results: dict[str, str] = {}
        consensus_text = ""

        for attempt in range(max_iterations):
            tasks = [
                self._call_with_retry(p, prompt, 1)
                for p in strategy.providers
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            answers: list[str] = []
            for provider, response in zip(strategy.providers, responses):
                text = str(response) if not isinstance(response, Exception) else ""
                provider_results[provider] = text
                if text:
                    answers.append(text)

            # Check if all agree (first 200 chars match)
            if answers:
                first = answers[0][:200].strip()
                if all(a[:200].strip() == first for a in answers):
                    consensus_text = answers[0]
                    return MOAResult(
                        mode=MOAExecutionMode.CONSENSUS,
                        provider_results=provider_results,
                        final_answer=consensus_text,
                        confidence=1.0,
                        consensus=True,
                        attempts=attempt + 1,
                    )

        # No consensus, synthesize
        final = self._synthesize(list(provider_results.values()))
        return MOAResult(
            mode=MOAExecutionMode.CONSENSUS,
            provider_results=provider_results,
            final_answer=final,
            confidence=0.3,
            consensus=False,
            attempts=max_iterations,
        )

    async def _execute_judge(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Use a judge model to evaluate and select the best answer."""
        if not self._model_caller or not strategy.judge_provider:
            return MOAResult(mode=MOAExecutionMode.JUDGE, final_answer="")

        # Get answers from all providers (except judge)
        worker_providers = [
            p for p in strategy.providers if p != strategy.judge_provider
        ]
        tasks = [
            self._call_with_retry(p, prompt, strategy.max_retries)
            for p in worker_providers
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        provider_results: dict[str, str] = {}
        for provider, response in zip(worker_providers, responses):
            provider_results[provider] = (
                str(response) if not isinstance(response, Exception) else ""
            )

        # Judge evaluates all answers
        judge_prompt = (
            f"Original prompt: {prompt}\n\n"
            f"Here are {len(provider_results)} different answers:\n"
        )
        for i, (provider, answer) in enumerate(provider_results.items()):
            judge_prompt += f"\nAnswer {i+1} (from {provider}):\n{answer[:500]}\n"
        judge_prompt += "\nSelect the best answer and explain why. Then output the best answer."

        judge_response = await self._call_with_retry(
            strategy.judge_provider, judge_prompt, 1
        )

        return MOAResult(
            mode=MOAExecutionMode.JUDGE,
            provider_results=provider_results,
            final_answer=judge_response,
            confidence=0.8,
            judge_feedback=judge_response,
        )

    async def _execute_critic(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Have one model answer, a critic evaluate, then improve."""
        if not self._model_caller or len(strategy.providers) < 2:
            return MOAResult(mode=MOAExecutionMode.CRITIC, final_answer="")

        # First provider answers
        primary = strategy.providers[0]
        initial = await self._call_with_retry(primary, prompt, strategy.max_retries)

        # Second provider critiques
        critic = strategy.providers[1] if len(strategy.providers) > 1 else primary
        critique_prompt = (
            f"Original request: {prompt}\n\n"
            f"Answer to critique:\n{initial}\n\n"
            f"Evaluate this answer critically. Identify any issues, errors, "
            f"or areas for improvement. Be specific."
        )
        critique = await self._call_with_retry(critic, critique_prompt, 1)

        # Third provider improves (or first again)
        improver = strategy.providers[2] if len(strategy.providers) > 2 else primary
        improve_prompt = (
            f"Original request: {prompt}\n\n"
            f"Initial answer:\n{initial}\n\n"
            f"Critique:\n{critique}\n\n"
            f"Provide an improved final answer that addresses the critique."
        )
        improved = await self._call_with_retry(improver, improve_prompt, 1)

        return MOAResult(
            mode=MOAExecutionMode.CRITIC,
            provider_results={
                primary: initial,
                critic: critique,
                improver: improved,
            },
            final_answer=improved,
            confidence=0.85,
            judge_feedback=critique,
        )

    async def _execute_synthesize(
        self, prompt: str, strategy: MOAStrategy, system: str
    ) -> MOAResult:
        """Get answers from all providers and synthesize into one."""
        if not self._model_caller:
            return MOAResult(mode=MOAExecutionMode.SYNTHESIZE, final_answer="")

        tasks = [
            self._call_with_retry(p, prompt, strategy.max_retries)
            for p in strategy.providers
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        provider_results: dict[str, str] = {}
        for provider, response in zip(strategy.providers, responses):
            provider_results[provider] = (
                str(response) if not isinstance(response, Exception) else ""
            )

        # Synthesize: use the last provider as synthesizer
        if len(strategy.providers) >= 2:
            synthesizer = strategy.providers[-1]
            synth_prompt = (
                f"Original prompt: {prompt}\n\n"
                f"Here are multiple perspectives:\n"
            )
            for provider, answer in provider_results.items():
                if provider != synthesizer:
                    synth_prompt += f"\n--- {provider} ---\n{answer[:500]}\n"
            synth_prompt += "\nSynthesize these into a single comprehensive answer."

            final = await self._call_with_retry(synthesizer, synth_prompt, 1)
        else:
            final = self._synthesize(list(provider_results.values()))

        return MOAResult(
            mode=MOAExecutionMode.SYNTHESIZE,
            provider_results=provider_results,
            final_answer=final,
            confidence=0.75,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self, provider: str, prompt: str, max_retries: int
    ) -> str:
        """Call a model with retry logic."""
        if not self._model_caller:
            return f"[{provider}] No model caller available."

        last_error = ""
        for attempt in range(max_retries):
            try:
                return await self._model_caller(provider, prompt)
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))

        return f"[{provider}] ERROR (after {max_retries} attempts): {last_error}"

    @staticmethod
    def _synthesize(answers: list[str]) -> str:
        """Simple synthesis: return the longest distinct answer."""
        if not answers:
            return ""
        # Remove error-like answers
        valid = [a for a in answers if not a.startswith("ERROR")]
        if not valid:
            return answers[0] if answers else ""
        # Return longest
        return max(valid, key=len)

    @staticmethod
    def _compute_confidence(answers: list[str]) -> float:
        """Estimate confidence based on answer agreement."""
        if not answers:
            return 0.0
        if len(answers) == 1:
            return 0.7
        # Compare first 100 chars of each
        stripped = [a[:100].strip().lower() for a in answers if a]
        if not stripped:
            return 0.0
        most_common = Counter(stripped).most_common(1)[0][1]
        return most_common / len(stripped)

    @staticmethod
    def _estimate_cost(strategy: MOAStrategy) -> float:
        """Estimate cost based on provider count and mode."""
        base = len(strategy.providers) * 0.002
        if strategy.mode in (MOAExecutionMode.CRITIC, MOAExecutionMode.JUDGE):
            base *= 2.0
        return base

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 10) -> list[MOAResult]:
        """Get recent execution history."""
        return self._execution_history[-limit:]

    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get MOA engine statistics."""
        if not self._execution_history:
            return {"total_executions": 0}

        modes = Counter(r.mode.value for r in self._execution_history)
        avg_confidence = sum(r.confidence for r in self._execution_history) / len(self._execution_history)
        avg_latency = sum(r.total_latency_ms for r in self._execution_history) / len(self._execution_history)

        return {
            "total_executions": len(self._execution_history),
            "mode_distribution": dict(modes),
            "avg_confidence": avg_confidence,
            "avg_latency_ms": avg_latency,
        }
