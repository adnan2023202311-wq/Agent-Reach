"""
Prompts layer: Prompt Library (M6.6).

Layer: Application/Core — depends inward on domain/ only.

Provides a registry for prompt templates with versioning, variable
substitution, metadata, and evaluation metadata.

A prompt template is a named, versioned string with ``{{ variable }}``
placeholders. The registry stores:
- prompt templates (with variables)
- versioning (monotonic per name)
- metadata (description, tags, owner)
- evaluation metadata (expected output, evaluation criteria)

This is distinct from agent system prompts (which are hardcoded in
agent classes). The Prompt Library is for *user-facing* prompts that
can be reused across conversations, workflows, and evaluations.

Design notes
------------
- Variable substitution uses the same ``{{ var }}`` syntax as the M5
  workflow template engine, but is intentionally simpler: no nested
  paths, no arithmetic, no conditionals. Prompts are text, not code.
- Versioning is monotonic per name (like WorkflowRegistry). Re-registering
  the same name bumps the version counter.
- Evaluation metadata is optional — a prompt may or may not have
  expected output / criteria attached.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Regex for {{ variable }} placeholders. Matches {{ name }} where name
# is a non-empty sequence of word characters or underscores.
_VARIABLE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass
class PromptTemplate:
    """A versioned prompt template.

    Attributes:
        prompt_id: unique identifier.
        name: human-readable name (unique per version).
        template: the prompt text with {{ variable }} placeholders.
        variables: list of variable names extracted from the template.
        version: monotonic version number (1-based, per name).
        description: short description.
        tags: arbitrary string tags.
        owner: owner/author identifier.
        metadata: arbitrary additional metadata.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
    """

    prompt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    template: str = ""
    variables: list[str] = field(default_factory=list)
    version: int = 1
    description: str = ""
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "prompt_id": self.prompt_id,
            "name": self.name,
            "template": self.template,
            "variables": list(self.variables),
            "version": self.version,
            "description": self.description,
            "tags": list(self.tags),
            "owner": self.owner,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PromptEvaluationMetadata:
    """Evaluation metadata for a prompt template.

    Attributes:
        expected_output: expected model output (for evaluation).
        criteria: list of evaluation criteria names.
        threshold: minimum score threshold (0.0–1.0).
        notes: free-form notes.
    """

    expected_output: str = ""
    criteria: list[str] = field(default_factory=list)
    threshold: float = 0.8
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "expected_output": self.expected_output,
            "criteria": list(self.criteria),
            "threshold": self.threshold,
            "notes": self.notes,
        }


class PromptLibrary:
    """Registry for versioned prompt templates.

    Supports registration, versioning, variable substitution,
    evaluation metadata, and discovery.
    """

    def __init__(self) -> None:
        self._prompts: dict[str, PromptTemplate] = {}
        self._by_id: dict[str, PromptTemplate] = {}
        self._versions: dict[str, int] = {}
        self._evaluations: dict[str, PromptEvaluationMetadata] = {}

    # ---------------------------------------------------------------------------
    # Registration
    # ---------------------------------------------------------------------------

    def register(
        self,
        name: str,
        template: str,
        *,
        description: str = "",
        tags: Optional[list[str]] = None,
        owner: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> PromptTemplate:
        """Register or update a prompt template.

        If a prompt with the same name already exists, its version is
        bumped and the template/metadata are updated. The prompt_id is
        preserved.

        Returns the registered PromptTemplate.
        """
        now = datetime.now(timezone.utc).isoformat()
        variables = self._extract_variables(template)

        if name in self._prompts:
            # Update existing — preserve prompt_id and created_at.
            existing = self._prompts[name]
            existing.template = template
            existing.variables = variables
            existing.description = description or existing.description
            existing.tags = list(tags) if tags is not None else existing.tags
            existing.owner = owner or existing.owner
            existing.metadata = dict(metadata) if metadata is not None else existing.metadata
            existing.version = self._versions.get(name, 0) + 1
            existing.updated_at = now
            self._versions[name] = existing.version
            prompt = existing
        else:
            version = self._versions.get(name, 0) + 1
            self._versions[name] = version
            prompt = PromptTemplate(
                name=name,
                template=template,
                variables=variables,
                version=version,
                description=description,
                tags=list(tags or []),
                owner=owner,
                metadata=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self._prompts[name] = prompt
            self._by_id[prompt.prompt_id] = prompt

        logger.info("Registered prompt: %s (v%d)", name, prompt.version)
        return prompt

    def unregister(self, name: str) -> bool:
        """Remove a prompt template.

        Returns True if the prompt was removed, False if it was not
        registered.
        """
        prompt = self._prompts.pop(name, None)
        if prompt is None:
            return False
        self._by_id.pop(prompt.prompt_id, None)
        # Keep the version counter — it is monotonic per name.
        self._evaluations.pop(prompt.prompt_id, None)
        logger.info("Unregistered prompt: %s", name)
        return True

    # ---------------------------------------------------------------------------
    # Evaluation metadata
    # ---------------------------------------------------------------------------

    def set_evaluation(
        self,
        name: str,
        expected_output: str = "",
        criteria: Optional[list[str]] = None,
        threshold: float = 0.8,
        notes: str = "",
    ) -> Optional[PromptEvaluationMetadata]:
        """Attach evaluation metadata to a prompt.

        Returns the evaluation metadata, or None if the prompt is not
        registered.
        """
        prompt = self._prompts.get(name)
        if prompt is None:
            return None
        eval_meta = PromptEvaluationMetadata(
            expected_output=expected_output,
            criteria=list(criteria or []),
            threshold=threshold,
            notes=notes,
        )
        self._evaluations[prompt.prompt_id] = eval_meta
        return eval_meta

    def get_evaluation(self, name: str) -> Optional[PromptEvaluationMetadata]:
        """Return the evaluation metadata for a prompt, or None."""
        prompt = self._prompts.get(name)
        if prompt is None:
            return None
        return self._evaluations.get(prompt.prompt_id)

    # ---------------------------------------------------------------------------
    # Variable substitution
    # ---------------------------------------------------------------------------

    def render(self, name: str, variables: dict[str, Any]) -> str:
        """Render a prompt template with variable substitution.

        Replaces ``{{ variable }}`` placeholders with values from the
        ``variables`` dict. Missing variables are left as-is (the
        placeholder is not replaced) so callers can detect incomplete
        substitutions.

        Raises
        ------
        KeyError:
            If the prompt is not registered.
        """
        prompt = self._prompts.get(name)
        if prompt is None:
            raise KeyError(f"Prompt '{name}' is not registered")

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            return match.group(0)  # leave unreplaced

        return _VARIABLE_RE.sub(replacer, prompt.template)

    def render_strict(self, name: str, variables: dict[str, Any]) -> str:
        """Render a prompt template, raising on missing variables.

        Raises
        ------
        KeyError:
            If the prompt is not registered or a variable is missing.
        """
        prompt = self._prompts.get(name)
        if prompt is None:
            raise KeyError(f"Prompt '{name}' is not registered")

        missing = [v for v in prompt.variables if v not in variables]
        if missing:
            raise KeyError(
                f"Missing variables for prompt '{name}': {missing}"
            )

        return self.render(name, variables)

    # ---------------------------------------------------------------------------
    # Access
    # ---------------------------------------------------------------------------

    def get(self, name: str) -> Optional[PromptTemplate]:
        """Return a prompt template by name, or None."""
        return self._prompts.get(name)

    def get_by_id(self, prompt_id: str) -> Optional[PromptTemplate]:
        """Return a prompt template by ID, or None."""
        return self._by_id.get(prompt_id)

    def get_version(self, name: str) -> int:
        """Return the current version for a name (0 if unregistered)."""
        return self._versions.get(name, 0)

    def list_prompts(
        self,
        *,
        tag: str = "",
        owner: str = "",
    ) -> list[PromptTemplate]:
        """List prompt templates, optionally filtered."""
        results: list[PromptTemplate] = []
        for prompt in self._prompts.values():
            if tag and tag not in prompt.tags:
                continue
            if owner and prompt.owner != owner:
                continue
            results.append(prompt)
        return sorted(results, key=lambda p: p.name)

    def list_names(self) -> list[str]:
        """Return all registered prompt names, sorted."""
        return sorted(self._prompts.keys())

    def list_tags(self) -> list[str]:
        """Return all distinct tags, sorted."""
        tags: set[str] = set()
        for prompt in self._prompts.values():
            tags.update(prompt.tags)
        return sorted(tags)

    def search(self, query: str) -> list[PromptTemplate]:
        """Search prompts by name, description, or tags (case-insensitive)."""
        q = query.lower()
        results: list[PromptTemplate] = []
        for prompt in self._prompts.values():
            if (
                q in prompt.name.lower()
                or q in prompt.description.lower()
                or any(q in t.lower() for t in prompt.tags)
            ):
                results.append(prompt)
        return sorted(results, key=lambda p: p.name)

    # ---------------------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        with_eval = sum(
            1 for p in self._prompts.values() if p.prompt_id in self._evaluations
        )
        return {
            "total": len(self._prompts),
            "with_evaluation": with_eval,
            "tags": len(self.list_tags()),
        }

    # ---------------------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------------------

    @staticmethod
    def _extract_variables(template: str) -> list[str]:
        """Extract unique variable names from a template, in order of first appearance."""
        seen: set[str] = set()
        variables: list[str] = []
        for match in _VARIABLE_RE.finditer(template):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                variables.append(name)
        return variables

    def clear(self) -> None:
        """Remove all prompts. Useful for testing."""
        self._prompts.clear()
        self._by_id.clear()
        self._versions.clear()
        self._evaluations.clear()
