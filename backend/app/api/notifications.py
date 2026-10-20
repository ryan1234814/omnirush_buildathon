"""In-app notification list and read-state endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import Notification, NotificationReadPatch
from app.storage import load_notifications, save_notifications

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[Notification])
async def list_notifications(
    request: Request, unread: bool = Query(default=False)
) -> list[Notification]:
    """Return stored notifications, newest first, optionally filtered to unread."""

    settings = request.app.state.settings
    notifications = load_notifications(settings.runs_dir)
    if unread:
        notifications = [item for item in notifications if not item.read]
    return notifications


@router.patch("/{notification_id}", response_model=Notification)
async def patch_notification(
    notification_id: str, payload: NotificationReadPatch, request: Request
) -> Notification:
    """Update the read flag of one stored notification."""

    settings = request.app.state.settings
    notifications = load_notifications(settings.runs_dir)
    for index, item in enumerate(notifications):
        if item.id == notification_id:
            updated = item.model_copy(update={"read": payload.read})
            notifications[index] = updated
            save_notifications(notifications, settings.runs_dir)
            return updated
    raise HTTPException(status_code=404, detail="Notification not found")
