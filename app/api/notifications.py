from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.notification import Notification, NotificationType, NotificationPriority

router = APIRouter(prefix="/notifications", tags=["Signaleringen"])


class NotificationOut(BaseModel):
    id: int
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    vehicle_id: Optional[int]
    customer_id: Optional[int]
    work_order_id: Optional[int]
    is_read: bool
    read_at: Optional[datetime]
    assigned_to: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = Query(False),
    priority: Optional[NotificationPriority] = None,
    assigned_to: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(Notification)
    if unread_only:
        q = q.where(Notification.is_read == False)
    if priority:
        q = q.where(Notification.priority == priority)
    if assigned_to:
        q = q.where(Notification.assigned_to == assigned_to)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Notification.id)).where(Notification.is_read == False)
    )
    return {"count": result.scalar()}


@router.patch("/{notification_id}/read")
async def mark_as_read(notification_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    notif = result.scalar_one_or_none()
    if notif and not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(tz=timezone.utc)
        await db.flush()
    return {"ok": True}


@router.patch("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update
    await db.execute(
        update(Notification)
        .where(Notification.is_read == False)
        .values(is_read=True, read_at=datetime.now(tz=timezone.utc))
    )
    await db.flush()
    return {"ok": True}
