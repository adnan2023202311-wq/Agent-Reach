"""
Skill Ecosystem (M7.6).

Enhanced skill management with discovery, versioning, dependencies,
metadata, composition, testing, and marketplace integration.

Extends the existing SkillEngine and SkillRegistry from Milestone 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from skills.engine import Skill, SkillEngine, SkillRegistry, SkillResult


@dataclass
class SkillMetadata:
    """Extended metadata for a skill."""

    author: str = ""
    license_: str = ""
    homepage: str = ""
    repository: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)
    rating: float = 0.0
    downloads: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SkillDependency:
    """A dependency of a skill."""

    skill_id: str
    version: str = "*"  # Semver constraint
    optional: bool = False


@dataclass
class SkillComposition:
    """A composition of multiple skills into a pipeline."""

    id: str = ""
    name: str = ""
    skills: list[str] = field(default_factory=list)  # Ordered skill IDs
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillEcosystem:
    """Enhanced skill management with ecosystem features.

    Extends SkillEngine with:
    - Discovery (by category, tag, rating)
    - Versioning support
    - Dependency management
    - Composition (skill pipelines)
    - Testing support
    - Marketplace integration metadata
    """

    def __init__(self) -> None:
        self._engine = SkillEngine()
        self._metadata: dict[str, SkillMetadata] = {}
        self._dependencies: dict[str, list[SkillDependency]] = {}
        self._compositions: dict[str, SkillComposition] = {}
        self._versions: dict[str, list[str]] = {}  # skill_name -> [version_ids]

    @property
    def registry(self) -> SkillRegistry:
        return self._engine.registry

    # ------------------------------------------------------------------
    # Registration with metadata
    # ------------------------------------------------------------------

    def register(
        self,
        skill: Skill,
        metadata: Optional[SkillMetadata] = None,
        dependencies: Optional[list[SkillDependency]] = None,
    ) -> None:
        """Register a skill with extended metadata and dependencies."""
        self._engine.registry.register(skill)
        if metadata:
            self._metadata[skill.id] = metadata
        if dependencies:
            self._dependencies[skill.id] = list(dependencies)

        # Track versions by name
        name_key = skill.name or skill.id
        self._versions.setdefault(name_key, []).append(skill.id)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
        *,
        category: str = "",
        tags: Optional[list[str]] = None,
        min_rating: float = 0.0,
        author: str = "",
    ) -> list[Skill]:
        """Discover skills by metadata filters."""
        results: list[Skill] = []
        for skill in self.registry.list_skills():
            meta = self._metadata.get(skill.id)
            if meta is None:
                continue

            if category and meta.category != category:
                continue
            if tags and not any(t in meta.tags for t in tags):
                continue
            if min_rating > 0 and meta.rating < min_rating:
                continue
            if author and meta.author != author:
                continue

            results.append(skill)

        return results

    def search(self, query: str) -> list[Skill]:
        """Search skills by name, description, or tags."""
        q = query.lower()
        results: list[Skill] = []
        for skill in self.registry.list_skills():
            meta = self._metadata.get(skill.id)
            if (
                q in skill.name.lower()
                or q in (skill.description or "").lower()
                or (meta and any(q in t.lower() for t in meta.tags))
            ):
                results.append(skill)
        return results

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def get_dependencies(self, skill_id: str) -> list[SkillDependency]:
        """Get the dependencies of a skill."""
        return list(self._dependencies.get(skill_id, []))

    def validate_dependencies(self, skill_id: str) -> list[str]:
        """Validate that all dependencies of a skill are registered.

        Returns list of missing dependency skill IDs.
        """
        missing: list[str] = []
        for dep in self._dependencies.get(skill_id, []):
            if dep.optional:
                continue
            if self.registry.get(dep.skill_id) is None:
                missing.append(dep.skill_id)
        return missing

    def resolve_dependencies(self, skill_id: str) -> list[Skill]:
        """Recursively resolve all dependencies of a skill.

        Returns ordered list of skills (dependencies first).
        """
        resolved: list[Skill] = []
        visited: set[str] = set()

        def _resolve(sid: str) -> None:
            if sid in visited:
                return
            visited.add(sid)
            for dep in self._dependencies.get(sid, []):
                if not dep.optional:
                    _resolve(dep.skill_id)
            skill = self.registry.get(sid)
            if skill and skill not in resolved:
                resolved.append(skill)

        _resolve(skill_id)
        return resolved

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def get_versions(self, skill_name: str) -> list[Skill]:
        """Get all versions of a skill by name."""
        version_ids = self._versions.get(skill_name, [])
        return [
            s for s in (self.registry.get(vid) for vid in version_ids) if s is not None
        ]

    def get_latest_version(self, skill_name: str) -> Optional[Skill]:
        """Get the latest version of a skill by name."""
        versions = self.get_versions(skill_name)
        if not versions:
            return None
        return versions[-1]  # Most recently registered

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(
        self,
        name: str,
        skill_ids: list[str],
        description: str = "",
    ) -> SkillComposition:
        """Create a skill composition (pipeline)."""
        composition = SkillComposition(
            id=name,
            name=name,
            skills=list(skill_ids),
            description=description,
        )
        self._compositions[composition.id] = composition
        return composition

    def get_composition(self, composition_id: str) -> Optional[SkillComposition]:
        """Get a composition by ID."""
        return self._compositions.get(composition_id)

    async def execute_composition(
        self,
        composition_id: str,
        inputs: dict[str, Any] | None = None,
    ) -> list[SkillResult]:
        """Execute all skills in a composition sequentially."""
        composition = self._compositions.get(composition_id)
        if composition is None:
            return [
                SkillResult(
                    skill_id=composition_id,
                    success=False,
                    error=f"Composition '{composition_id}' not found",
                )
            ]

        results: list[SkillResult] = []
        current_inputs = inputs or {}

        for skill_id in composition.skills:
            result = await self._engine.execute(skill_id, current_inputs)
            results.append(result)
            if not result.success:
                break
            # Pass output as input to next skill
            if result.output is not None:
                current_inputs = {"previous_output": result.output, **current_inputs}

        return results

    # ------------------------------------------------------------------
    # Testing
    # ------------------------------------------------------------------

    async def test_skill(
        self,
        skill_id: str,
        test_inputs: dict[str, Any],
        expected_output: Any = None,
    ) -> dict[str, Any]:
        """Test a skill with given inputs and optionally check output."""
        result = await self._engine.execute(skill_id, test_inputs)
        passed = result.success
        if passed and expected_output is not None:
            passed = result.output == expected_output
        return {
            "skill_id": skill_id,
            "passed": passed,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "expected": expected_output,
        }

    # ------------------------------------------------------------------
    # Marketplace
    # ------------------------------------------------------------------

    def export_manifest(self, skill_id: str) -> Optional[dict[str, Any]]:
        """Export a skill's marketplace manifest."""
        skill = self.registry.get(skill_id)
        if skill is None:
            return None

        meta = self._metadata.get(skill_id, SkillMetadata())
        deps = [
            {"skill_id": d.skill_id, "version": d.version, "optional": d.optional}
            for d in self._dependencies.get(skill_id, [])
        ]

        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "parameters": skill.parameters,
            "author": meta.author,
            "license": meta.license_,
            "category": meta.category,
            "tags": meta.tags,
            "dependencies": deps,
            "input_schema": meta.input_schema,
            "output_schema": meta.output_schema,
            "examples": meta.examples,
        }

    # ------------------------------------------------------------------
    # Stats & Cleanup
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get ecosystem statistics."""
        skills = self.registry.list_skills()
        categories: dict[str, int] = {}
        for skill in skills:
            meta = self._metadata.get(skill.id)
            if meta and meta.category:
                categories[meta.category] = categories.get(meta.category, 0) + 1

        return {
            "total_skills": len(skills),
            "total_compositions": len(self._compositions),
            "total_versions": sum(len(v) for v in self._versions.values()),
            "categories": categories,
            "with_dependencies": len(self._dependencies),
            "with_metadata": len(self._metadata),
        }

    def clear(self) -> None:
        """Clear all registrations."""
        self._engine.clear()
        self._metadata.clear()
        self._dependencies.clear()
        self._compositions.clear()
        self._versions.clear()
