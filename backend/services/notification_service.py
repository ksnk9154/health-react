"""Notification service — create / list / mark-read user notifications.

Notifications are event-driven side-effects of domain actions (document
upload, extraction, health-report generation, record changes, abnormal lab
values, deletion).  Every query is filtered by ``user_id`` so one user can
never read another user's notifications.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update

from db.models import Notification
from db.session import get_db_session

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dump_data(data: Optional[dict]) -> Optional[str]:
    if not data:
        return None
    try:
        return json.dumps(data)
    except (TypeError, ValueError):
        return None


def _parse_data(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def create_notification(
    user_id: int,
    message: str,
    type: str = "info",
    title: Optional[str] = None,
    data: Optional[dict] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[Notification]:
    """Create a notification for ``user_id``.

    If ``dedupe_key`` is supplied and the user already has an *unread*
    notification with that key, the existing one is refreshed (newer timestamp
    + updated payload) instead of spawning a duplicate.  All failures are
    swallowed — a notification failure must never break the originating action.
    """
    session = get_db_session()
    try:
        if dedupe_key:
            existing = session.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.dedupe_key == dedupe_key,
                    Notification.is_read.is_(False),
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.title = title
                existing.message = message
                existing.type = type
                existing.data = _dump_data(data)
                existing.created_at = _now_iso()
                session.commit()
                session.refresh(existing)
                return existing

        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            data=_dump_data(data),
            dedupe_key=dedupe_key,
            is_read=False,
            created_at=_now_iso(),
        )
        session.add(notif)
        session.commit()
        session.refresh(notif)
        return notif
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        logger.exception("create_notification failed for user=%s", user_id)
        return None
    finally:
        session.close()


def list_notifications(
    user_id: int,
    limit: int = 50,
    unread_only: Optional[bool] = None,
) -> list:
    """Return the ``limit`` most recent notifications for ``user_id``."""
    session = get_db_session()
    try:
        q = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        rows = session.execute(q).scalars().all()
        return [_serialize(n) for n in rows]
    except Exception:
        logger.exception("list_notifications failed for user=%s", user_id)
        return []
    finally:
        session.close()


def get_unread_count(user_id: int) -> int:
    """Return the number of unread notifications for ``user_id``."""
    session = get_db_session()
    try:
        return session.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        ).scalar() or 0
    except Exception:
        logger.exception("get_unread_count failed for user=%s", user_id)
        return 0
    finally:
        session.close()


def mark_read(notification_id: int, user_id: int) -> bool:
    """Mark a single notification as read. Returns True if it existed."""
    session = get_db_session()
    try:
        notif = session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        ).scalar_one_or_none()
        if notif is None:
            return False
        notif.is_read = True
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.exception("mark_read failed for id=%s user=%s", notification_id, user_id)
        return False
    finally:
        session.close()


def mark_all_read(user_id: int) -> int:
    """Mark every notification for ``user_id`` as read. Returns rows updated."""
    session = get_db_session()
    try:
        updated = session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        ).rowcount
        session.commit()
        return updated or 0
    except Exception:
        session.rollback()
        logger.exception("mark_all_read failed for user=%s", user_id)
        return 0
    finally:
        session.close()


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "user_id": n.user_id,
        "title": n.title,
        "message": n.message,
        "type": n.type,
        "data": _parse_data(n.data),
        "is_read": bool(n.is_read),
        "created_at": n.created_at,
    }

