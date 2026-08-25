"""Notification API routes — ``/api/notifications``.

All endpoints are authenticated and strictly user-scoped: ``user_id`` is taken
from the JWT (never from the request body), and every query is filtered by it,
so one user can never read or mutate another user's notifications.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.deps import get_current_user
from services.notification_service import (
    get_unread_count,
    list_notifications,
    mark_all_read,
    mark_read,
)

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    user_id: int
    title: Optional[str] = None
    message: str
    type: str
    data: Optional[dict] = None
    is_read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


@router.get(
    "/",
    response_model=NotificationListResponse,
    summary="List the current user's notifications",
)
def list_endpoint(
    current_user=Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    unread_only: Optional[bool] = Query(default=None),
):
    uid = current_user["id"]
    items = list_notifications(uid, limit=limit, unread_only=unread_only)
    return NotificationListResponse(
        items=items, total=len(items), unread_count=get_unread_count(uid)
    )


@router.post("/{notification_id}/read", summary="Mark a notification as read")
def mark_read_endpoint(notification_id: int, current_user=Depends(get_current_user)):
    ok = mark_read(notification_id, current_user["id"])
    return {"success": ok}


@router.post("/mark-all-read", summary="Mark all of the current user's notifications as read")
def mark_all_read_endpoint(current_user=Depends(get_current_user)):
    updated = mark_all_read(current_user["id"])
    return {"success": True, "updated": updated}
