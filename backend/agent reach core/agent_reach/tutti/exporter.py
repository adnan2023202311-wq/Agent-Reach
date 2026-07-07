"""
Tutti-inspired Portable Context (M7.11).

Export and import complete workspace state for portability
across different AI systems and platforms.

Features:
- Export Complete Workspace State
- Import Workspace State
- Resume Session Anywhere
- Cross Platform Context (Claude, ChatGPT, Codex, future AI)
- Portable Context Package

Layer: Application/Core.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TargetPlatform(str, Enum):
    """Target AI platforms for context export."""
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    CODEX = "codex"
    GENERIC = "generic"
    AGENT_REACH = "agent_reach"


@dataclass
class PortableContext:
    """A portable context package that can be exported and imported.

    Contains the complete state of a workspace: conversations,
    memories, knowledge, skills, workflows, and platform metadata.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "1.0"
    created_at: str = ""
    source_platform: str = "agent_reach"
    target_platform: TargetPlatform = TargetPlatform.GENERIC

    # Core context
    system_prompt: str = ""
    conversation: list[dict[str, str]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)

    # Extended context
    skills: list[dict[str, Any]] = field(default_factory=list)
    workflows: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "created_at": self.created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_platform": self.source_platform,
            "target_platform": self.target_platform.value,
            "system_prompt": self.system_prompt,
            "conversation": list(self.conversation),
            "memories": list(self.memories),
            "knowledge": list(self.knowledge),
            "skills": list(self.skills),
            "workflows": list(self.workflows),
            "files": list(self.files),
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> PortableContext:
        """Deserialize from JSON string."""
        d = json.loads(data)
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PortableContext:
        """Create from a dictionary."""
        target = TargetPlatform(d.get("target_platform", "generic"))
        return cls(
            id=d.get("id", ""),
            version=d.get("version", "1.0"),
            created_at=d.get("created_at", ""),
            source_platform=d.get("source_platform", "agent_reach"),
            target_platform=target,
            system_prompt=d.get("system_prompt", ""),
            conversation=d.get("conversation", []),
            memories=d.get("memories", []),
            knowledge=d.get("knowledge", []),
            skills=d.get("skills", []),
            workflows=d.get("workflows", []),
            files=d.get("files", []),
            metadata=d.get("metadata", {}),
        )


class TuttiExporter:
    """Export and import portable context packages.

    Supports conversion between different AI platform formats.
    """

    def __init__(self) -> None:
        self._exports: dict[str, PortableContext] = {}

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_context(
        self,
        target: TargetPlatform = TargetPlatform.GENERIC,
        system_prompt: str = "",
        conversation: list[dict[str, str]] | None = None,
        memories: list[dict[str, Any]] | None = None,
        knowledge: list[dict[str, Any]] | None = None,
        skills: list[dict[str, Any]] | None = None,
        workflows: list[dict[str, Any]] | None = None,
        files: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PortableContext:
        """Create a portable context package from workspace state.

        Args:
            target: Target platform for the export.
            system_prompt: System prompt/instructions.
            conversation: Conversation history.
            memories: Memory items.
            knowledge: Knowledge entries.
            skills: Skill definitions.
            workflows: Workflow definitions.
            files: File references.

        Returns:
            PortableContext ready for export.
        """
        ctx = PortableContext(
            source_platform="agent_reach",
            target_platform=target,
            system_prompt=system_prompt,
            conversation=list(conversation or []),
            memories=list(memories or []),
            knowledge=list(knowledge or []),
            skills=list(skills or []),
            workflows=list(workflows or []),
            files=list(files or []),
            metadata=dict(metadata or {}),
        )

        self._exports[ctx.id] = ctx
        return ctx

    def export_to_json(
        self,
        target: TargetPlatform = TargetPlatform.GENERIC,
        **kwargs: Any,
    ) -> str:
        """Export context directly to JSON string."""
        ctx = self.export_context(target=target, **kwargs)
        return ctx.to_json()

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_context(self, data: str | dict[str, Any]) -> PortableContext:
        """Import a portable context from JSON or dict.

        Args:
            data: JSON string or dictionary.

        Returns:
            Imported PortableContext.
        """
        if isinstance(data, str):
            ctx = PortableContext.from_json(data)
        else:
            ctx = PortableContext.from_dict(data)

        self._exports[ctx.id] = ctx
        return ctx

    def import_for_resume(self, data: str | dict[str, Any]) -> dict[str, Any]:
        """Import context and prepare for session resumption.

        Returns a dict with conversation, memories, system prompt,
        and other state that can be directly used to resume a session.
        """
        ctx = self.import_context(data)

        return {
            "system_prompt": ctx.system_prompt,
            "conversation": list(ctx.conversation),
            "memories": list(ctx.memories),
            "knowledge": list(ctx.knowledge),
            "skills": list(ctx.skills),
            "metadata": dict(ctx.metadata),
            "context_id": ctx.id,
        }

    # ------------------------------------------------------------------
    # Platform Conversion
    # ------------------------------------------------------------------

    def convert_for_platform(
        self,
        ctx: PortableContext,
        target: TargetPlatform,
    ) -> PortableContext:
        """Convert a context package for a different AI platform.

        Adjusts format to match the target platform's conventions.
        """
        converted = PortableContext(
            source_platform=ctx.source_platform,
            target_platform=target,
            system_prompt=ctx.system_prompt,
            conversation=list(ctx.conversation),
            metadata=dict(ctx.metadata),
        )

        if target == TargetPlatform.CHATGPT:
            converted.metadata["format"] = "openai_chat"
            converted.metadata["instructions"] = ctx.system_prompt
        elif target == TargetPlatform.CLAUDE:
            converted.metadata["format"] = "anthropic_messages"
        elif target == TargetPlatform.CODEX:
            converted.metadata["format"] = "codex_session"

        # For non-AgentReach platforms, include memories inline
        if target != TargetPlatform.AGENT_REACH and ctx.memories:
            memory_text = "\n".join(
                str(m.get("content", "")) for m in ctx.memories
            )
            converted.system_prompt = (
                f"{ctx.system_prompt}\n\nRelevant context:\n{memory_text}"
            )

        return converted

    # ------------------------------------------------------------------
    # Session utilities
    # ------------------------------------------------------------------

    def create_resume_package(
        self,
        session_id: str,
        conversation: list[dict[str, str]],
        system_prompt: str = "",
        memories: list[dict[str, Any]] | None = None,
    ) -> PortableContext:
        """Create a package optimized for session resumption."""
        return self.export_context(
            target=TargetPlatform.AGENT_REACH,
            system_prompt=system_prompt,
            conversation=conversation,
            memories=memories,
            metadata={
                "session_id": session_id,
                "resume": True,
                "created_for_resume": True,
            },
        )

    def get_export(self, export_id: str) -> Optional[PortableContext]:
        """Retrieve a previously exported context."""
        return self._exports.get(export_id)

    def list_exports(self) -> list[dict[str, str]]:
        """List all exported contexts."""
        return [
            {"id": cid, "target": ctx.target_platform.value, "created": ctx.created_at}
            for cid, ctx in self._exports.items()
        ]

    def clear(self) -> None:
        """Clear all exports."""
        self._exports.clear()
