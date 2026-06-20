"""
Signaleringstaak: controleert de database op situaties die actie vereisen
en maakt notificaties aan.
"""

from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle, Appointment, WorkOrder, Notification, Checklist
from app.models.vehicle import VehicleStatus
from app.models.work_order import WorkOrderStatus
from app.models.appointment import AppointmentStatus
from app.models.notification import NotificationType, NotificationPriority


def _now():
    return datetime.now(tz=timezone.utc)


async def run_alert_checks(db: AsyncSession):
    """Voer alle signaleringschecks uit."""
    checks = [
        _check_apk_expiry(db),
        _check_vehicles_stuck_in_prep(db),
        _check_incomplete_checklists(db),
        _check_upcoming_appointments(db),
        _check_vehicles_without_checklist(db),
    ]
    for check in checks:
        try:
            await check
        except Exception as e:
            logger.error(f"Alert check mislukt: {e}")


async def _notification_exists(db: AsyncSession, notif_type: NotificationType, vehicle_id: int) -> bool:
    """Voorkom dubbele notificaties (zelfde type + voertuig vandaag)."""
    today = _now().date()
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.notification_type == notif_type,
                Notification.vehicle_id == vehicle_id,
                Notification.created_at >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
            )
        )
    )
    return result.scalar_one_or_none() is not None


async def _check_apk_expiry(db: AsyncSession):
    """Signaleer voertuigen waarvan de APK bijna verloopt of al verlopen is."""
    soon = _now().date() + timedelta(days=30)
    today = _now().date()

    result = await db.execute(
        select(Vehicle).where(
            Vehicle.apk_expiry.is_not(None),
            Vehicle.status != VehicleStatus.VERKOCHT,
        )
    )
    vehicles = result.scalars().all()

    for v in vehicles:
        if not v.apk_expiry:
            continue

        expiry = v.apk_expiry if isinstance(v.apk_expiry, type(today)) else v.apk_expiry

        if expiry < today:
            if not await _notification_exists(db, NotificationType.APK_VERLOPEN, v.id):
                db.add(Notification(
                    notification_type=NotificationType.APK_VERLOPEN,
                    priority=NotificationPriority.URGENT,
                    title=f"APK VERLOPEN — {v.make} {v.model} ({v.license_plate})",
                    message=f"De APK van {v.license_plate} is verlopen op {expiry}. Direct actie vereist.",
                    vehicle_id=v.id,
                ))
        elif expiry <= soon:
            if not await _notification_exists(db, NotificationType.APK_BIJNA_VERLOPEN, v.id):
                dagen = (expiry - today).days
                db.add(Notification(
                    notification_type=NotificationType.APK_BIJNA_VERLOPEN,
                    priority=NotificationPriority.HOOG,
                    title=f"APK verloopt binnenkort — {v.license_plate}",
                    message=f"De APK van {v.make} {v.model} ({v.license_plate}) verloopt over {dagen} dagen ({expiry}).",
                    vehicle_id=v.id,
                ))

    await db.flush()
    logger.debug("APK-check uitgevoerd")


async def _check_vehicles_stuck_in_prep(db: AsyncSession):
    """Signaleer voertuigen die al meer dan 14 dagen in voorbereiding zijn."""
    threshold = _now() - timedelta(days=14)

    result = await db.execute(
        select(Vehicle).where(
            Vehicle.status == VehicleStatus.IN_VOORBEREIDING,
            Vehicle.updated_at < threshold,
        )
    )
    vehicles = result.scalars().all()

    for v in vehicles:
        if not await _notification_exists(db, NotificationType.INKOOP_ACTIE_VEREIST, v.id):
            db.add(Notification(
                notification_type=NotificationType.INKOOP_ACTIE_VEREIST,
                priority=NotificationPriority.HOOG,
                title=f"Voertuig {v.license_plate} al lang in voorbereiding",
                message=f"{v.make} {v.model} ({v.license_plate}) staat al meer dan 14 dagen in voorbereiding. Controleer de status.",
                vehicle_id=v.id,
            ))

    await db.flush()
    logger.debug("Voorbereiding-check uitgevoerd")


async def _check_incomplete_checklists(db: AsyncSession):
    """Signaleer checklists die al meer dan 3 dagen niet compleet zijn."""
    threshold = _now() - timedelta(days=3)

    result = await db.execute(
        select(Checklist).where(
            Checklist.completed_at.is_(None),
            Checklist.created_at < threshold,
        )
    )
    checklists = result.scalars().all()

    for cl in checklists:
        if not await _notification_exists(db, NotificationType.CHECKLIST_NIET_COMPLEET, cl.vehicle_id):
            db.add(Notification(
                notification_type=NotificationType.CHECKLIST_NIET_COMPLEET,
                priority=NotificationPriority.NORMAAL,
                title=f"Checklist niet compleet: {cl.title}",
                message=f"Checklist '{cl.title}' is al meer dan 3 dagen niet afgerond.",
                vehicle_id=cl.vehicle_id,
            ))

    await db.flush()
    logger.debug("Checklist-check uitgevoerd")


async def _check_upcoming_appointments(db: AsyncSession):
    """Stuur herinneringen voor afspraken van morgen."""
    tomorrow_start = _now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
    tomorrow_end = tomorrow_start + timedelta(days=1)

    result = await db.execute(
        select(Appointment).where(
            Appointment.start_time >= tomorrow_start,
            Appointment.start_time < tomorrow_end,
            Appointment.status == AppointmentStatus.GEPLAND,
            Appointment.reminder_sent == False,
        )
    )
    appointments = result.scalars().all()

    for appt in appointments:
        db.add(Notification(
            notification_type=NotificationType.AFSPRAAK_HERINNERING,
            priority=NotificationPriority.NORMAAL,
            title=f"Afspraak morgen: {appt.appointment_type.value}",
            message=f"Morgen om {appt.start_time.strftime('%H:%M')} is er een {appt.appointment_type.value} afspraak.",
            vehicle_id=appt.vehicle_id,
            customer_id=appt.customer_id,
        ))
        appt.reminder_sent = True

    await db.flush()
    logger.debug(f"Afspraak-herinneringen: {len(appointments)} verstuurd")


async def _check_vehicles_without_checklist(db: AsyncSession):
    """Voertuigen die ingekocht zijn maar nog geen inkoop-checklist hebben."""
    from sqlalchemy import not_, exists
    from app.models.checklist import ChecklistType

    subquery = select(Checklist.vehicle_id).where(
        Checklist.checklist_type == ChecklistType.INKOOP_CONTROLE
    )

    result = await db.execute(
        select(Vehicle).where(
            Vehicle.status == VehicleStatus.INGEKOCHT,
            not_(Vehicle.id.in_(subquery)),
        )
    )
    vehicles = result.scalars().all()

    for v in vehicles:
        from app.tasks.checklist_factory import create_vehicle_checklist
        await create_vehicle_checklist(db, v, "inkoop_controle")
        logger.info(f"Automatische inkoop-checklist aangemaakt voor {v.license_plate}")
