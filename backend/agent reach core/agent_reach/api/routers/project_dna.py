"""
API layer: /api/v1/project-dna — Project DNA (M10.35).

Analyzes project patterns, conventions, and structure to build a
"DNA" profile that can be used for templates, consistency checks,
and intelligent defaults.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/project-dna", tags=["project-dna"])


class ProjectDNA(BaseModel):
    dna_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    language: str = "python"
    framework: str = ""  # fastapi | django | flask | react | next
    patterns: dict[str, Any] = Field(default_factory=dict)
    conventions: dict[str, Any] = Field(default_factory=dict)
    structure: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    test_framework: str = ""
    created_at: float = Field(default_factory=time.time)


class ProjectTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    dna_id: str = ""  # source DNA
    file_structure: dict[str, Any] = Field(default_factory=dict)
    config_files: dict[str, str] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time())


_dnas: dict[str, ProjectDNA] = {}
_templates: dict[str, ProjectTemplate] = {}


class AnalyzeDNARequest(BaseModel):
    project_name: str
    files: list[dict[str, str]] = Field(default_factory=list)  # [{"path": "...", "content": "..."}]


@router.post("/analyze")
async def analyze_dna(request: AnalyzeDNARequest) -> dict[str, Any]:
    """Analyze a project's structure and conventions to build its DNA."""
    import re
    patterns: dict[str, Any] = {}
    conventions: dict[str, Any] = {}
    structure: dict[str, Any] = {}
    dependencies: list[str] = []
    language = "python"
    framework = ""
    test_framework = ""

    for file_info in request.files:
        path = file_info.get("path", "")
        content = file_info.get("content", "")
        # Detect language
        if path.endswith(".py"):
            language = "python"
        elif path.endswith(".ts") or path.endswith(".tsx"):
            language = "typescript"
        elif path.endswith(".js") or path.endswith(".jsx"):
            language = "javascript"
        # Detect framework
        if "fastapi" in content.lower():
            framework = "fastapi"
        elif "django" in content.lower():
            framework = "django"
        elif "react" in content.lower():
            framework = "react"
        # Extract dependencies
        if path.endswith("requirements.txt") or path.endswith("pyproject.toml"):
            dependencies = [line.strip() for line in content.split("\n") if line.strip() and not line.startswith("#")]
        elif path == "package.json":
            import json
            try:
                pkg = json.loads(content)
                dependencies = list(pkg.get("dependencies", {}).keys())
            except Exception:
                pass
        # Detect test framework
        if "pytest" in content:
            test_framework = "pytest"
        elif "jest" in content.lower():
            test_framework = "jest"
        # Build structure
        parts = path.split("/")
        current = structure
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = True

    # Infer conventions
    conventions["naming"] = "snake_case" if language == "python" else "camelCase"
    conventions["indent"] = "4 spaces" if language == "python" else "2 spaces"
    conventions["test_naming"] = "test_*.py" if language == "python" else "*.test.*"

    dna = ProjectDNA(
        project_name=request.project_name, language=language, framework=framework,
        patterns=patterns, conventions=conventions, structure=structure,
        dependencies=dependencies, test_framework=test_framework,
    )
    _dnas[dna.dna_id] = dna
    return dna.model_dump()


@router.get("/dnas")
async def list_dnas() -> dict[str, Any]:
    return {"dnas": [d.model_dump() for d in _dnas.values()], "count": len(_dnas)}


@router.get("/dnas/{dna_id}")
async def get_dna(dna_id: str) -> dict[str, Any]:
    dna = _dnas.get(dna_id)
    if dna is None:
        raise HTTPException(status_code=404, detail="DNA not found")
    return dna.model_dump()


class CreateTemplateRequest(BaseModel):
    name: str
    description: str = ""
    dna_id: str = ""


@router.post("/templates")
async def create_template(request: CreateTemplateRequest) -> dict[str, Any]:
    """Create a project template from a DNA profile."""
    template = ProjectTemplate(
        name=request.name, description=request.description, dna_id=request.dna_id,
        file_structure=_dnas.get(request.dna_id, ProjectDNA(project_name="")).structure if request.dna_id else {},
        config_files={},
    )
    _templates[template.template_id] = template
    return {"template_id": template.template_id, "name": template.name, "status": "created"}


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    return {"templates": [t.model_dump() for t in _templates.values()], "count": len(_templates)}


@router.get("/stats")
async def dna_stats() -> dict[str, Any]:
    from collections import Counter
    lang_counts = Counter(d.language for d in _dnas.values())
    fw_counts = Counter(d.framework for d in _dnas.values() if d.framework)
    return {
        "total_dnas": len(_dnas),
        "total_templates": len(_templates),
        "by_language": dict(lang_counts),
        "by_framework": dict(fw_counts),
    }
