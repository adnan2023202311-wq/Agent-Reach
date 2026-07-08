"""
API layer: /api/v1/adapters — Future AI Layer (M9.26).

Layer: Interface/Presentation.

Exposes the AdapterRegistry: category interface descriptions,
registered adapters, and activation of runtime-activatable
categories. Registration of adapter OBJECTS happens in Python
(plugins, composition root, tests) — the API surface is for
introspection and activation, since an adapter cannot be transported
as JSON.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from infrastructure.adapters import (
    AdapterActivationUnsupported,
    AdapterRegistry,
)

router = APIRouter(prefix="/api/v1/adapters", tags=["adapters"])


def _registry(request: Request) -> AdapterRegistry:
    registry = getattr(request.app.state, "adapter_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Adapter registry not available")
    return registry


@router.get("/categories")
async def adapter_categories() -> dict[str, Any]:
    """The required interface per adapter category."""
    return AdapterRegistry.describe_categories()


@router.get("")
async def list_adapters(request: Request, category: str = "") -> dict[str, Any]:
    adapters = _registry(request).list_adapters(category=category)
    return {"items": [a.to_dict() for a in adapters], "count": len(adapters)}


@router.post("/{category}/{name}/activate")
async def activate_adapter(category: str, name: str, request: Request) -> dict[str, Any]:
    """Bind a registered adapter into the live runtime."""
    registry = _registry(request)
    try:
        registered = registry.activate(category, name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "ADAPTER_NOT_FOUND"},
        ) from exc
    except AdapterActivationUnsupported as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "code": "ACTIVATION_UNSUPPORTED"},
        ) from exc
    return registered.to_dict()
