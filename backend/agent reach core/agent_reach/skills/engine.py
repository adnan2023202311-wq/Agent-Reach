"""
Skill Engine for Milestone 4.

Per ADR-001: Plugins contain Skills. Plugins are containers.
Business logic belongs inside Skills.

A Skill is a reusable, versioned unit of business logic that can be
registered, discovered, and executed by the SkillEngine.

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Skill:
    """A reusable, versioned unit of business logic.

    Attributes:
        id: Unique skill identifier
        name: Human-readable name
        description: What this skill does
        version: Semantic version string
        parameters: Expected input parameter schema
        executor: Async callable that implements the skill
        metadata: Additional type-specific metadata
    """

    id: str
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    parameters: dict[str, Any] = field(default_factory=dict)
    executor: Callable[..., Awaitable[Any]] = field(default=lambda **kwargs: None)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    """Outcome of executing a skill."""

    skill_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class SkillRegistry:
    """Registry for skill discovery and lookup."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill."""
        self._skills[skill.id] = skill

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill registration."""
        if skill_id not in self._skills:
            return False
        del self._skills[skill_id]
        return True

    def get(self, skill_id: str) -> Optional[Skill]:
        """Retrieve a skill by ID."""
        return self._skills.get(skill_id)

    def list_skills(self) -> list[Skill]:
        """List all registered skills."""
        return list(self._skills.values())

    def find_by_name(self, name: str) -> list[Skill]:
        """Find skills matching a name."""
        return [s for s in self._skills.values() if s.name == name]

    def clear(self) -> None:
        """Remove all skills. Useful for testing."""
        self._skills.clear()


class SkillEngine:
    """Executes skills with validation and exception isolation.

    The SkillEngine is the runtime counterpart to SkillRegistry.
    It resolves skills and runs them, producing SkillResults.
    """

    def __init__(self, registry: Optional[SkillRegistry] = None) -> None:
        self._registry = registry or SkillRegistry()

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    async def execute(self, skill_id: str, inputs: dict[str, Any] | None = None) -> SkillResult:
        """Execute a skill by ID with the given inputs.

        Args:
            skill_id: The skill to execute
            inputs: Keyword arguments passed to the skill executor

        Returns:
            SkillResult with output or error
        """
        start = time.perf_counter()
        skill = self._registry.get(skill_id)
        if skill is None:
            return SkillResult(
                skill_id=skill_id,
                success=False,
                error=f"Skill '{skill_id}' not found",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        try:
            output = await skill.executor(**(inputs or {}))
            return SkillResult(
                skill_id=skill_id,
                success=True,
                output=output,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            return SkillResult(
                skill_id=skill_id,
                success=False,
                error=f"Skill execution failed: {exc}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    async def execute_batch(
        self,
        tasks: list[tuple[str, dict[str, Any] | None]],
    ) -> list[SkillResult]:
        """Execute multiple skills sequentially.

        Args:
            tasks: List of (skill_id, inputs) tuples

        Returns:
            List of SkillResults in the same order
        """
        results: list[SkillResult] = []
        for skill_id, inputs in tasks:
            result = await self.execute(skill_id, inputs)
            results.append(result)
        return results

    def clear(self) -> None:
        """Clear the underlying registry."""
        self._registry.clear()
