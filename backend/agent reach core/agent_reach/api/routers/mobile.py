"""
API layer: /api/v1/mobile — Mobile Companion (M10.11).

Provides the API surface for native iOS and Android companion apps.
The mobile app is a lightweight client that connects to the same
backend, offering real-time monitoring, push notifications, and
quick-action chat.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile-companion"])


class DeviceRegistration(BaseModel):
    device_id: str
    platform: str = Field(..., description="ios or android")
    push_token: str = ""
    app_version: str = "1.0.0"
    user_id: str = ""


class MobileNotification(BaseModel):
    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    sent_at: float = Field(default_factory=time.time)
    read: bool = False


_devices: dict[str, DeviceRegistration] = {}
_notifications: list[MobileNotification] = []


@router.post("/devices/register")
async def register_device(request: DeviceRegistration) -> dict[str, Any]:
    """Register a mobile device for push notifications."""
    _devices[request.device_id] = request
    return {"device_id": request.device_id, "status": "registered", "platform": request.platform}


@router.delete("/devices/{device_id}")
async def unregister_device(device_id: str) -> dict[str, Any]:
    """Unregister a mobile device."""
    if _devices.pop(device_id, None) is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "unregistered"}


@router.get("/devices")
async def list_devices(platform: Optional[str] = None) -> dict[str, Any]:
    """List registered mobile devices."""
    devices = list(_devices.values())
    if platform:
        devices = [d for d in devices if d.platform == platform]
    return {"devices": [d.model_dump() for d in devices], "count": len(devices)}


@router.post("/notifications/send")
async def send_notification(device_id: str, title: str, body: str, data: Optional[dict] = None) -> dict[str, Any]:
    """Send a push notification to a registered device."""
    if device_id not in _devices:
        raise HTTPException(status_code=404, detail="Device not registered")
    notif = MobileNotification(
        device_id=device_id, title=title, body=body, data=data or {},
    )
    _notifications.append(notif)
    return {"notification_id": notif.notification_id, "status": "sent"}


@router.get("/notifications/{device_id}")
async def get_notifications(device_id: str, unread_only: bool = False) -> dict[str, Any]:
    """Get notifications for a device."""
    notifs = [n for n in _notifications if n.device_id == device_id]
    if unread_only:
        notifs = [n for n in notifs if not n.read]
    return {"notifications": [n.model_dump() for n in notifs], "count": len(notifs)}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str) -> dict[str, Any]:
    """Mark a notification as read."""
    for n in _notifications:
        if n.notification_id == notification_id:
            n.read = True
            return {"status": "read"}
    raise HTTPException(status_code=404, detail="Notification not found")


@router.get("/quick-actions")
async def quick_actions() -> dict[str, Any]:
    """Return available quick actions for the mobile app home screen."""
    return {
        "actions": [
            {"id": "new-chat", "label": "New Chat", "icon": "chat", "endpoint": "/api/v1/chat"},
            {"id": "new-conversation", "label": "New Conversation", "icon": "conversation", "endpoint": "/api/v1/conversations/sessions"},
            {"id": "view-agents", "label": "Agents", "icon": "agents", "endpoint": "/api/v1/agents"},
            {"id": "marketplace", "label": "Marketplace", "icon": "market", "endpoint": "/api/v1/marketplace/v2/items"},
            {"id": "observatory", "label": "Observatory", "icon": "observatory", "endpoint": "/api/v1/observatory/live"},
            {"id": "settings", "label": "Settings", "icon": "settings", "endpoint": "/api/v1/providers"},
        ]
    }


@router.get("/manifest")
async def mobile_manifest() -> dict[str, Any]:
    """Mobile app manifest — version, features, minimum OS versions."""
    return {
        "app_version": "1.0.0",
        "min_ios_version": "15.0",
        "min_android_version": "8.0 (API 26)",
        "features": ["chat", "notifications", "monitoring", "quick-actions"],
        "push_notifications": True,
        "offline_cache": True,
        "biometric_auth": True,
    }
