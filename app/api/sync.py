from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db, AsyncSessionLocal
from app.models.sync_log import SyncLog, SyncSource, SyncStatus

router = APIRouter(prefix="/sync", tags=["Synchronisatie"])


class SyncLogOut(BaseModel):
    id: int
    source: SyncSource
    status: SyncStatus
    started_at: datetime
    finished_at: Optional[datetime]
    records_created: int
    records_updated: int
    records_failed: int
    error_message: Optional[str]

    class Config:
        from_attributes = True


async def _run_sync(source: str):
    async with AsyncSessionLocal() as db:
        try:
            if source == "gaston":
                from app.tasks.sync import sync_gaston
                await sync_gaston(db)
            elif source == "sam":
                from app.tasks.sync import sync_sam
                await sync_sam(db)
            elif source == "vwe":
                from app.tasks.sync import sync_vwe
                await sync_vwe(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise


@router.post("/gaston")
async def trigger_gaston_sync(background_tasks: BackgroundTasks):
    """Start een handmatige Gaston synchronisatie."""
    background_tasks.add_task(_run_sync, "gaston")
    return {"message": "Gaston synchronisatie gestart"}


@router.post("/sam")
async def trigger_sam_sync(background_tasks: BackgroundTasks):
    """Start een handmatige SAM synchronisatie."""
    background_tasks.add_task(_run_sync, "sam")
    return {"message": "SAM synchronisatie gestart"}


@router.post("/vwe")
async def trigger_vwe_sync(background_tasks: BackgroundTasks):
    """Start een handmatige VWE synchronisatie."""
    background_tasks.add_task(_run_sync, "vwe")
    return {"message": "VWE synchronisatie gestart"}


@router.post("/all")
async def trigger_all_sync(background_tasks: BackgroundTasks):
    """Start synchronisatie van alle systemen."""
    for source in ["gaston", "sam", "vwe"]:
        background_tasks.add_task(_run_sync, source)
    return {"message": "Alle synchronisaties gestart"}


@router.get("/logs", response_model=list[SyncLogOut])
async def get_sync_logs(
    source: Optional[SyncSource] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    q = select(SyncLog)
    if source:
        q = q.where(SyncLog.source == source)
    q = q.order_by(SyncLog.started_at.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()
