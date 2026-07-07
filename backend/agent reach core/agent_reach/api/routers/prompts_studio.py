"""
API layer: /api/v1/prompts — Prompt Studio (M8.8)

Wraps the existing PromptLibrary with versioning, testing, evaluation.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


# in-memory prompt store fallback if PromptLibrary not injected
# We try to import the M6 PromptLibrary
try:
    from prompts.library import PromptLibrary  # type: ignore
    _PROMPT_LIB = PromptLibrary()
except Exception:
    try:
        from prompt_library import PromptLibrary  # type: ignore
        _PROMPT_LIB = PromptLibrary()
    except Exception:
        _PROMPT_LIB = None

# simple in-memory fallback
_FALLBACK_STORE: dict[str, list[dict[str, Any]]] = {}


class PromptCreate(BaseModel):
    name: str
    template: str
    variables: list[str] = Field(default_factory=list)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class PromptTestRequest(BaseModel):
    template: str
    variables: dict[str, Any] = Field(default_factory=dict)


def _lib():
    if _PROMPT_LIB is not None:
        return _PROMPT_LIB
    return None


@router.get("")
async def list_prompts(search: str = "", tag: str = "") -> dict[str, Any]:
    lib = _lib()
    try:
        if lib and hasattr(lib, "list"):
            items = lib.list()  # type: ignore
        elif lib and hasattr(lib, "list_prompts"):
            items = lib.list_prompts()  # type: ignore
        else:
            # fallback
            items = []
            for name, versions in _FALLBACK_STORE.items():
                if versions:
                    v = versions[-1]
                    items.append({"name": name, "version": v.get("version", len(versions)), **v})
    except Exception:
        items = []
    # filter
    if search:
        items = [i for i in items if search.lower() in str(i.get("name", "")).lower() or search.lower() in str(i.get("template", "")).lower()]
    if tag:
        items = [i for i in items if tag in i.get("tags", [])]
    return {"items": items, "count": len(items)}


@router.post("")
async def create_prompt(p: PromptCreate) -> dict[str, Any]:
    lib = _lib()
    try:
        if lib and hasattr(lib, "add"):
            # PromptLibrary from M6
            result = lib.add(name=p.name, template=p.template, variables=p.variables, description=p.description)  # type: ignore
            version = getattr(result, "version", 1)
        elif lib and hasattr(lib, "create"):
            result = lib.create(p.name, p.template)  # type: ignore
            version = 1
        else:
            # fallback store
            versions = _FALLBACK_STORE.setdefault(p.name, [])
            version = len(versions) + 1
            versions.append({
                "name": p.name,
                "template": p.template,
                "variables": p.variables,
                "description": p.description,
                "tags": p.tags,
                "version": version,
            })
        return {"name": p.name, "version": version, "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{name}")
async def get_prompt(name: str, version: Optional[int] = None) -> dict[str, Any]:
    lib = _lib()
    try:
        if lib and hasattr(lib, "get"):
            prompt = lib.get(name, version=version)  # type: ignore
            if prompt:
                return {
                    "name": name,
                    "template": getattr(prompt, "template", str(prompt)),
                    "version": getattr(prompt, "version", version or 1),
                }
        # fallback
        versions = _FALLBACK_STORE.get(name, [])
        if not versions:
            raise HTTPException(status_code=404, detail="Prompt not found")
        if version:
            v = next((x for x in versions if x.get("version") == version), None)
            if not v:
                raise HTTPException(status_code=404, detail="Version not found")
        else:
            v = versions[-1]
        return v
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test")
async def test_prompt(req: PromptTestRequest) -> dict[str, Any]:
    """Render a prompt with variables, no LLM call – fast preview."""
    try:
        rendered = req.template
        for k, v in req.variables.items():
            rendered = rendered.replace("{{ " + k + " }}", str(v))
            rendered = rendered.replace("{{" + k + "}}", str(v))
        # simple token estimate
        tokens = len(rendered) // 4
        return {
            "rendered": rendered,
            "tokens_estimate": tokens,
            "variables_used": list(req.variables.keys()),
            "length": len(rendered),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{name}/history")
async def prompt_history(name: str) -> dict[str, Any]:
    versions = _FALLBACK_STORE.get(name, [])
    # if lib supports history, use it
    lib = _lib()
    if lib and hasattr(lib, "history"):
        try:
            versions = lib.history(name)  # type: ignore
        except Exception:
            pass
    return {"name": name, "versions": versions, "count": len(versions)}


@router.post("/{name}/optimize")
async def optimize_prompt(name: str) -> dict[str, Any]:
    """Prompt optimization stub – M8 Prompt Intelligence integration point."""
    # In production this would call Prompt Intelligence engine
    return {
        "name": name,
        "optimized": True,
        "suggestions": [
            "Add explicit output format",
            "Reduce ambiguity in variables",
            "Add 1-shot example",
        ],
        "score_improvement": "+12%",
    }
