"""
APScheduler-configuratie voor periodieke sync- en signaleringstaak.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.config import settings
from app.database import AsyncSessionLocal
from app.tasks.sync import sync_gaston, sync_sam, sync_vwe
from app.tasks.alerts import run_alert_checks


scheduler = AsyncIOScheduler(timezone="Europe/Amsterdam")


async def _run_gaston_sync():
    async with AsyncSessionLocal() as db:
        try:
            await sync_gaston(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Gaston sync taak fout: {e}")


async def _run_sam_sync():
    async with AsyncSessionLocal() as db:
        try:
            await sync_sam(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"SAM sync taak fout: {e}")


async def _run_vwe_sync():
    async with AsyncSessionLocal() as db:
        try:
            await sync_vwe(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"VWE sync taak fout: {e}")


async def _run_alert_checks():
    async with AsyncSessionLocal() as db:
        try:
            await run_alert_checks(db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Alert check taak fout: {e}")


def setup_scheduler():
    """Registreer alle geplande taken."""

    scheduler.add_job(
        _run_gaston_sync,
        trigger=IntervalTrigger(minutes=settings.gaston_sync_interval),
        id="gaston_sync",
        name="Gaston synchronisatie",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        _run_sam_sync,
        trigger=IntervalTrigger(minutes=settings.sam_sync_interval),
        id="sam_sync",
        name="SAM synchronisatie",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        _run_vwe_sync,
        trigger=IntervalTrigger(minutes=settings.vwe_sync_interval),
        id="vwe_sync",
        name="VWE synchronisatie",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Signaleringen elk uur
    scheduler.add_job(
        _run_alert_checks,
        trigger=IntervalTrigger(hours=1),
        id="alert_checks",
        name="Signalering & alertchecks",
        replace_existing=True,
        misfire_grace_time=600,
    )

    logger.info("Taakplanner geconfigureerd")
    return scheduler
