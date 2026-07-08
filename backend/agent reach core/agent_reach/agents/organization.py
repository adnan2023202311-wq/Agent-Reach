"""
AI Engineering Organization (M9.12).

Layer: Application — composes EXISTING machinery:

    Role execution   → the SHARED IntelligentPipeline (each role is a
                       framed pipeline request, like Agent Studio's
                       runs — same execution path, real traces)
    Coordination     → dependency-wave scheduling reusing the M9.29
                       CollaborationEngine's wave semantics: roles
                       whose inputs are ready run concurrently
    Communication    → the M3 AgentMessenger (real messages between
                       roles carrying upstream deliverables)
    Observability    → every role run carries the request_id of its
                       persisted M9.3 trace

The organization is a fixed role graph modeling the M9.12 chart
(CEO → Architect → Planner → Backend/Frontend/Research → QA/Security
→ DevOps → Documentation → Release Manager). Each role has a charter
(its system framing) and consumes the deliverables of its
dependencies. The output is a full project record: per-role
deliverables, timing, trace links, and the message audit trail.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from core.agent_communication import AgentMessage, AgentMessenger


@dataclass(frozen=True)
class RoleSpec:
    """One organizational role: charter + dependencies."""

    role: str
    charter: str
    depends_on: tuple[str, ...] = ()


# The M9.12 organization chart as a dependency graph.
ORGANIZATION_ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(
        "ceo",
        "You are the CEO. Define the business objective, success criteria, "
        "and constraints for this initiative. Be concrete and brief.",
    ),
    RoleSpec(
        "architect",
        "You are the Software Architect. Given the CEO's objective, design "
        "the technical approach: components, boundaries, data flow, and the "
        "key architectural decisions with their trade-offs.",
        depends_on=("ceo",),
    ),
    RoleSpec(
        "planner",
        "You are the Delivery Planner. Turn the architecture into an ordered "
        "implementation plan with milestones and explicit acceptance criteria.",
        depends_on=("architect",),
    ),
    RoleSpec(
        "backend_engineer",
        "You are the Backend Engineer. Implement the backend portion of the "
        "plan: describe the modules, interfaces, and code-level decisions.",
        depends_on=("planner",),
    ),
    RoleSpec(
        "frontend_engineer",
        "You are the Frontend Engineer. Implement the frontend portion of "
        "the plan: screens, state, and API consumption decisions.",
        depends_on=("planner",),
    ),
    RoleSpec(
        "research",
        "You are the Research Engineer. Identify the technical unknowns in "
        "the plan and resolve them with concrete findings.",
        depends_on=("planner",),
    ),
    RoleSpec(
        "qa",
        "You are the QA Engineer. Given the implementations, define the test "
        "strategy and enumerate the critical test cases and edge cases.",
        depends_on=("backend_engineer", "frontend_engineer"),
    ),
    RoleSpec(
        "security",
        "You are the Security Engineer. Review the implementations for "
        "security risks and specify the required mitigations.",
        depends_on=("backend_engineer", "frontend_engineer"),
    ),
    RoleSpec(
        "devops",
        "You are the DevOps Engineer. Define deployment, configuration, "
        "monitoring, and rollback for this system.",
        depends_on=("qa", "security"),
    ),
    RoleSpec(
        "documentation",
        "You are the Documentation Engineer. Produce the documentation "
        "outline covering setup, usage, and operations.",
        depends_on=("qa", "security"),
    ),
    RoleSpec(
        "release_manager",
        "You are the Release Manager. Given everything upstream, produce the "
        "release decision: readiness assessment, version, and release notes.",
        depends_on=("devops", "documentation"),
    ),
)


@dataclass
class RoleRun:
    """One role's real execution."""

    role: str
    status: str = "pending"  # pending | succeeded | failed
    deliverable: str = ""
    request_id: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "status": self.status,
            "deliverable": self.deliverable[:2000],
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class ProjectRecord:
    """One complete organizational project run."""

    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    objective: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    waves: list[list[str]] = field(default_factory=list)
    role_runs: dict[str, RoleRun] = field(default_factory=dict)
    messages_exchanged: int = 0
    status: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "objective": self.objective,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "waves": [list(w) for w in self.waves],
            "role_runs": {role: run.to_dict() for role, run in self.role_runs.items()},
            "messages_exchanged": self.messages_exchanged,
            "status": self.status,
        }


class EngineeringOrganization:
    """Run projects through the fixed multi-role organization."""

    def __init__(
        self,
        pipeline: Any,
        roles: Optional[tuple[RoleSpec, ...]] = None,
        messenger: Optional[AgentMessenger] = None,
        max_projects: int = 100,
    ) -> None:
        if max_projects < 1:
            raise ValueError("max_projects must be >= 1")
        self._pipeline = pipeline
        self._roles = roles if roles is not None else ORGANIZATION_ROLES
        self._validate_role_graph(self._roles)
        self._messenger = messenger or AgentMessenger()
        self._projects: dict[str, ProjectRecord] = {}
        self._max_projects = max_projects

    @property
    def messenger(self) -> AgentMessenger:
        return self._messenger

    def describe(self) -> dict[str, Any]:
        """The organization chart (roles + dependencies + waves)."""
        return {
            "roles": [
                {
                    "role": spec.role,
                    "charter": spec.charter,
                    "depends_on": list(spec.depends_on),
                }
                for spec in self._roles
            ],
            "waves": [
                [spec.role for spec in wave] for wave in self._build_waves()
            ],
        }

    # ── Execution ───────────────────────────────────────────────

    async def run_project(self, objective: str) -> ProjectRecord:
        """Run one objective through every role, wave by wave."""
        if not objective.strip():
            raise ValueError("objective must not be empty")

        record = ProjectRecord(objective=objective)
        record.role_runs = {spec.role: RoleRun(role=spec.role) for spec in self._roles}
        waves = self._build_waves()
        record.waves = [[spec.role for spec in wave] for wave in waves]

        for wave in waves:
            await asyncio.gather(
                *(self._run_role(spec, record) for spec in wave)
            )

        record.finished_at = time.time()
        succeeded = sum(
            1 for run in record.role_runs.values() if run.status == "succeeded"
        )
        record.status = "succeeded" if succeeded == len(record.role_runs) else (
            "partial" if succeeded else "failed"
        )
        self._projects[record.project_id] = record
        self._evict()
        return record

    async def _run_role(self, spec: RoleSpec, record: ProjectRecord) -> None:
        run = record.role_runs[spec.role]

        # Collect upstream deliverables and share them as REAL
        # messages through the M3 bus.
        upstream_sections: list[str] = []
        for dependency in spec.depends_on:
            dep_run = record.role_runs[dependency]
            if dep_run.status == "succeeded" and dep_run.deliverable:
                self._messenger.send(
                    AgentMessage(
                        sender=f"role:{dependency}",
                        recipient=f"role:{spec.role}",
                        message_type="deliverable",
                        payload={
                            "project_id": record.project_id,
                            "deliverable": dep_run.deliverable[:2000],
                        },
                    )
                )
                record.messages_exchanged += 1
                upstream_sections.append(
                    f"[{dependency} deliverable]\n{dep_run.deliverable[:2000]}"
                )

        prompt_parts = [f"[Charter: {spec.charter}]"]
        prompt_parts.extend(upstream_sections)
        prompt_parts.append(f"Objective: {record.objective}")
        framed = "\n\n".join(prompt_parts)

        start = time.perf_counter()
        try:
            result = await self._pipeline.process(
                framed,
                session_id=f"org:{record.project_id}",
                extra_context={"organization_role": spec.role},
            )
            run.deliverable = result.outcome.answer
            run.request_id = result.trace.request_id
            run.status = (
                "succeeded"
                if result.outcome.status.value == "succeeded"
                else "failed"
            )
        except Exception as exc:  # noqa: BLE001 — role isolation
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        run.latency_ms = (time.perf_counter() - start) * 1000

    # ── Introspection ───────────────────────────────────────────

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        return self._projects.get(project_id)

    def list_projects(self, limit: int = 20) -> list[ProjectRecord]:
        projects = sorted(
            self._projects.values(), key=lambda p: p.started_at, reverse=True
        )
        return projects[: max(0, limit)]

    def get_communications(self, project_id: str) -> list[dict[str, Any]]:
        """Real inter-role messages of one project."""
        return [
            {
                "id": m.id,
                "sender": m.sender,
                "recipient": m.recipient,
                "timestamp": m.timestamp,
                "deliverable_preview": str(m.payload.get("deliverable", ""))[:300],
            }
            for m in self._messenger.get_history(message_type="deliverable")
            if m.payload.get("project_id") == project_id
        ]

    def clear(self) -> None:
        self._projects.clear()
        self._messenger.clear_history()

    # ── Internals ───────────────────────────────────────────────

    def _build_waves(self) -> list[list[RoleSpec]]:
        pending = {spec.role: spec for spec in self._roles}
        resolved: set[str] = set()
        waves: list[list[RoleSpec]] = []
        while pending:
            wave = [
                spec for spec in pending.values()
                if all(dep in resolved for dep in spec.depends_on)
            ]
            if not wave:
                raise ValueError(f"Dependency cycle among roles: {sorted(pending)}")
            for spec in wave:
                del pending[spec.role]
                resolved.add(spec.role)
            waves.append(wave)
        return waves

    @staticmethod
    def _validate_role_graph(roles: tuple[RoleSpec, ...]) -> None:
        names = {spec.role for spec in roles}
        if len(names) != len(roles):
            raise ValueError("Duplicate role names in the organization")
        for spec in roles:
            unknown = [d for d in spec.depends_on if d not in names]
            if unknown:
                raise ValueError(
                    f"Role '{spec.role}' depends on unknown roles: {unknown}"
                )

    def _evict(self) -> None:
        while len(self._projects) > self._max_projects:
            oldest = min(self._projects.values(), key=lambda p: p.started_at)
            del self._projects[oldest.project_id]
