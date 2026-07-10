"""
API layer: /api/v1/repository — Repository Intelligence (M10.29).

Codebase graph + dependency analysis. Builds a semantic graph of the
repository's modules, their dependencies, and relationships. Enables
intelligent code search, impact analysis, and refactoring suggestions.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/repository", tags=["repository-intelligence"])


class CodeModule(BaseModel):
    module_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    path: str
    language: str = "python"  # python | typescript | javascript | etc.
    lines: int = 0
    functions: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    imported_by: list[str] = Field(default_factory=list)
    complexity_score: float = 0.0
    last_analyzed: float = 0.0


class DependencyEdge(BaseModel):
    source: str  # module path
    target: str  # module path
    edge_type: str = "import"  # import | inherit | call | reference
    strength: float = 1.0


_modules: dict[str, CodeModule] = {}
_dependencies: list[DependencyEdge] = []


class AnalyzeModuleRequest(BaseModel):
    path: str
    language: str = "python"
    content: str = ""


@router.post("/modules/analyze")
async def analyze_module(request: AnalyzeModuleRequest) -> dict[str, Any]:
    """Analyze a code module and extract its structure."""
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    lines = request.content.count("\n") + 1 if request.content else 0

    if request.language == "python":
        import re
        functions = re.findall(r"^\s*(?:async\s+)?def\s+(\w+)", request.content, re.MULTILINE)
        classes = re.findall(r"^\s*class\s+(\w+)", request.content, re.MULTILINE)
        imports = re.findall(r"^\s*(?:from\s+\S+\s+)?import\s+(.+)", request.content, re.MULTILINE)
    elif request.language in ("typescript", "javascript"):
        import re
        functions = re.findall(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", request.content)
        functions += re.findall(r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(", request.content)
        classes = re.findall(r"(?:export\s+)?class\s+(\w+)", request.content)
        imports = re.findall(r"import\s+.*from\s+[\"']([^\"']+)", request.content)

    # Simple complexity: lines / (functions + classes + 1)
    complexity = lines / (len(functions) + len(classes) + 1) if lines > 0 else 0

    module = CodeModule(
        path=request.path, language=request.language, lines=lines,
        functions=functions, classes=classes, imports=imports,
        complexity_score=round(complexity, 2),
        last_analyzed=time.time(),
    )
    _modules[module.path] = module
    return {"module": module.model_dump(), "status": "analyzed"}


@router.get("/modules")
async def list_modules(language: Optional[str] = None) -> dict[str, Any]:
    modules = list(_modules.values())
    if language:
        modules = [m for m in modules if m.language == language]
    return {"modules": [m.model_dump() for m in modules], "count": len(modules)}


@router.get("/modules/{path:path}")
async def get_module(path: str) -> dict[str, Any]:
    module = _modules.get(path)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    return module.model_dump()


class AddDependencyRequest(BaseModel):
    source: str
    target: str
    edge_type: str = "import"


@router.post("/dependencies")
async def add_dependency(request: AddDependencyRequest) -> dict[str, Any]:
    """Record a dependency between two modules."""
    edge = DependencyEdge(source=request.source, target=request.target, edge_type=request.edge_type)
    _dependencies.append(edge)
    # Update module imported_by
    if request.target in _modules:
        if request.source not in _modules[request.target].imported_by:
            _modules[request.target].imported_by.append(request.source)
    return {"status": "recorded", "edge": edge.model_dump()}


@router.get("/dependencies")
async def list_dependencies(module_path: Optional[str] = None) -> dict[str, Any]:
    deps = list(_dependencies)
    if module_path:
        deps = [d for d in deps if d.source == module_path or d.target == module_path]
    return {"dependencies": [d.model_dump() for d in deps], "count": len(deps)}


@router.get("/graph")
async def dependency_graph() -> dict[str, Any]:
    """Get the full dependency graph for visualization."""
    nodes = [{"id": m.path, "language": m.language, "lines": m.lines, "complexity": m.complexity_score}
             for m in _modules.values()]
    edges = [{"source": d.source, "target": d.target, "type": d.edge_type}
             for d in _dependencies]
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


@router.get("/impact/{module_path:path}")
async def impact_analysis(module_path: str) -> dict[str, Any]:
    """Analyze the impact of changing a module (what depends on it)."""
    if module_path not in _modules:
        raise HTTPException(status_code=404, detail="Module not found")
    # Find all modules that directly or transitively depend on this one
    direct = [d.source for d in _dependencies if d.target == module_path]
    transitive: set[str] = set()
    queue = list(direct)
    while queue:
        current = queue.pop(0)
        if current in transitive:
            continue
        transitive.add(current)
        for d in _dependencies:
            if d.target == current and d.source not in transitive:
                queue.append(d.source)
    return {
        "module": module_path,
        "directly_affected": direct,
        "transitively_affected": list(transitive - set(direct)),
        "total_impact": len(transitive),
    }


@router.get("/search")
async def search_code(query: str, limit: int = 10) -> dict[str, Any]:
    """Search across all analyzed modules."""
    query_lower = query.lower()
    results = []
    for module in _modules.values():
        score = 0
        if query_lower in module.path.lower():
            score += 5
        for fn in module.functions:
            if query_lower in fn.lower():
                score += 3
        for cls in module.classes:
            if query_lower in cls.lower():
                score += 3
        if score > 0:
            results.append({"module": module.path, "score": score, "language": module.language})
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"query": query, "results": results[:limit], "count": len(results)}


@router.get("/stats")
async def repository_stats() -> dict[str, Any]:
    from collections import Counter
    lang_counts = Counter(m.language for m in _modules.values())
    total_lines = sum(m.lines for m in _modules.values())
    avg_complexity = sum(m.complexity_score for m in _modules.values()) / max(1, len(_modules))
    return {
        "total_modules": len(_modules),
        "total_lines": total_lines,
        "total_dependencies": len(_dependencies),
        "by_language": dict(lang_counts),
        "avg_complexity": round(avg_complexity, 2),
        "most_complex": max(_modules.values(), key=lambda m: m.complexity_score).path if _modules else "",
    }
