"""
API layer: /api/v1/app-store — AI App Store (M10.19).

Public marketplace for AI applications. Supports publishing, ratings,
reviews, updates, and revenue sharing. Builds on M10.8 (AI Application
Builder) and M10.9 (Marketplace V2) — apps created via the builder can
be published to the app store for public discovery.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/app-store", tags=["ai-app-store"])


class StoreApp(BaseModel):
    app_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    developer: str
    description: str = ""
    category: str = "productivity"  # productivity | research | automation | education | entertainment | developer
    version: str = "1.0.0"
    price: float = 0.0  # 0.0 = free
    revenue_share_developer: float = 0.7  # 70% to developer, 30% to platform
    screenshots: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    install_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    published: bool = True
    verified: bool = False
    featured: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class Review(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str
    user_id: str
    rating: float = Field(..., ge=0, le=5)
    comment: str = ""
    timestamp: float = Field(default_factory=time.time)


_apps: dict[str, StoreApp] = {}
_user_installs: dict[str, list[str]] = {}  # user_id → [app_ids]
_revenue: dict[str, float] = {}  # developer → total_revenue


class PublishAppRequest(BaseModel):
    name: str
    developer: str
    description: str = ""
    category: str = "productivity"
    version: str = "1.0.0"
    price: float = 0.0
    tags: list[str] = Field(default_factory=list)


@router.post("/apps")
async def publish_app(request: PublishAppRequest) -> dict[str, Any]:
    """Publish an app to the store."""
    app = StoreApp(
        name=request.name, developer=request.developer, description=request.description,
        category=request.category, version=request.version, price=request.price, tags=request.tags,
    )
    _apps[app.app_id] = app
    return {"app_id": app.app_id, "name": app.name, "status": "published"}


@router.get("/apps")
async def browse_apps(
    category: Optional[str] = None,
    featured_only: bool = False,
    free_only: bool = False,
    query: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Browse the app store with filters."""
    apps = list(_apps.values())
    if category:
        apps = [a for a in apps if a.category == category]
    if featured_only:
        apps = [a for a in apps if a.featured]
    if free_only:
        apps = [a for a in apps if a.price == 0.0]
    if query:
        q = query.lower()
        apps = [a for a in apps if q in a.name.lower() or q in a.description.lower()]
    apps.sort(key=lambda a: (a.featured, a.install_count), reverse=True)
    return {
        "apps": [{k: v for k, v in a.model_dump().items() if k != "reviews"} for a in apps[:limit]],
        "count": len(apps),
    }


@router.get("/apps/{app_id}")
async def get_app(app_id: str) -> dict[str, Any]:
    """Get app details."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app.model_dump()


@router.post("/apps/{app_id}/install")
async def install_app(app_id: str, user_id: str) -> dict[str, Any]:
    """Install an app (tracks install count + revenue)."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.install_count += 1
    _user_installs.setdefault(user_id, []).append(app_id)
    # Revenue: developer gets 70%, platform gets 30%
    if app.price > 0:
        dev_share = app.price * app.revenue_share_developer
        _revenue[app.developer] = _revenue.get(app.developer, 0.0) + dev_share
    return {"app_id": app_id, "status": "installed", "install_count": app.install_count}


class SubmitReviewRequest(BaseModel):
    user_id: str
    rating: float = Field(..., ge=0, le=5)
    comment: str = ""


@router.post("/apps/{app_id}/reviews")
async def submit_review(app_id: str, request: SubmitReviewRequest) -> dict[str, Any]:
    """Submit a review for an app."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    review = Review(app_id=app_id, user_id=request.user_id, rating=request.rating, comment=request.comment)
    app.reviews.append(review.model_dump())
    # Update rating average
    total = app.rating * app.rating_count + request.rating
    app.rating_count += 1
    app.rating = total / app.rating_count
    return {"review_id": review.review_id, "app_rating": app.rating, "rating_count": app.rating_count}


@router.post("/apps/{app_id}/feature")
async def feature_app(app_id: str) -> dict[str, Any]:
    """Feature an app on the store homepage."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.featured = True
    return {"app_id": app_id, "featured": True}


@router.post("/apps/{app_id}/verify")
async def verify_app(app_id: str) -> dict[str, Any]:
    """Verify an app (blue checkmark)."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.verified = True
    return {"app_id": app_id, "verified": True}


class UpdateAppRequest(BaseModel):
    version: str
    description: str = ""


@router.put("/apps/{app_id}")
async def update_app(app_id: str, request: UpdateAppRequest) -> dict[str, Any]:
    """Push an update to a published app."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.version = request.version
    if request.description:
        app.description = request.description
    app.updated_at = time.time()
    return {"app_id": app_id, "version": app.version, "status": "updated"}


@router.get("/developer/{developer}/revenue")
async def developer_revenue(developer: str) -> dict[str, Any]:
    """Get revenue summary for a developer."""
    apps = [a for a in _apps.values() if a.developer == developer]
    total_installs = sum(a.install_count for a in apps)
    total_revenue = _revenue.get(developer, 0.0)
    return {
        "developer": developer,
        "apps_published": len(apps),
        "total_installs": total_installs,
        "total_revenue": round(total_revenue, 2),
        "revenue_share": "70% developer / 30% platform",
    }


@router.get("/categories")
async def app_categories() -> dict[str, Any]:
    """List app store categories."""
    return {
        "categories": [
            {"id": "productivity", "name": "Productivity", "description": "Apps that help you get things done"},
            {"id": "research", "name": "Research", "description": "Research and analysis assistants"},
            {"id": "automation", "name": "Automation", "description": "Workflow and task automation"},
            {"id": "education", "name": "Education", "description": "Learning and tutoring apps"},
            {"id": "entertainment", "name": "Entertainment", "description": "Creative and fun apps"},
            {"id": "developer", "name": "Developer Tools", "description": "Tools for software developers"},
        ]
    }


@router.get("/stats")
async def store_stats() -> dict[str, Any]:
    """App store aggregate statistics."""
    return {
        "total_apps": len(_apps),
        "total_installs": sum(a.install_count for a in _apps.values()),
        "total_revenue": round(sum(_revenue.values()), 2),
        "verified_apps": sum(1 for a in _apps.values() if a.verified),
        "featured_apps": sum(1 for a in _apps.values() if a.featured),
    }
