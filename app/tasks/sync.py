"""
Synchronisatie-taken: verwerkt data uit VWE, Gaston en SAM
en slaat deze op in de centrale CRM-database.
"""

from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.gaston import GastonConnector, GastonWorkOrder, GastonCustomer, GastonAppointment
from app.connectors.sam import SamConnector, SamVehicle, SamCustomer, SamSale
from app.connectors.vwe import VweConnector, VweVehicle
from app.models import Customer, Vehicle, WorkOrder, Appointment, SyncLog, Notification
from app.models.sync_log import SyncSource, SyncStatus
from app.models.vehicle import VehicleStatus
from app.models.work_order import WorkOrderStatus, WorkOrderType
from app.models.appointment import AppointmentType, AppointmentStatus
from app.models.notification import NotificationType, NotificationPriority
from app.tasks.checklist_factory import create_vehicle_checklist


# ──────────────────────────────────────────────────────────
# Hulpfuncties
# ──────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _map_gaston_order_type(raw: Optional[str]) -> WorkOrderType:
    if not raw:
        return WorkOrderType.REPARATIE
    raw = raw.lower()
    if "onderhoud" in raw:
        return WorkOrderType.ONDERHOUD
    if "apk" in raw:
        return WorkOrderType.APK
    if "voorbereiding" in raw or "prep" in raw:
        return WorkOrderType.VOORBEREIDING
    if "garantie" in raw:
        return WorkOrderType.GARANTIE
    if "schade" in raw:
        return WorkOrderType.SCHADE
    return WorkOrderType.REPARATIE


def _map_gaston_order_status(raw: Optional[str]) -> WorkOrderStatus:
    if not raw:
        return WorkOrderStatus.AANGEMELD
    raw = raw.lower()
    if "gepland" in raw or "ingepland" in raw:
        return WorkOrderStatus.INGEPLAND
    if "uitvoering" in raw or "bezig" in raw:
        return WorkOrderStatus.IN_UITVOERING
    if "wacht" in raw or "onderdelen" in raw:
        return WorkOrderStatus.WACHT_OP_ONDERDELEN
    if "gereed" in raw or "klaar" in raw or "afgerond" in raw:
        return WorkOrderStatus.GEREED
    if "gefactureerd" in raw or "factuur" in raw:
        return WorkOrderStatus.GEFACTUREERD
    if "geannuleerd" in raw:
        return WorkOrderStatus.GEANNULEERD
    return WorkOrderStatus.AANGEMELD


def _map_sam_vehicle_status(raw: Optional[str]) -> VehicleStatus:
    if not raw:
        return VehicleStatus.INGEKOCHT
    raw = raw.lower()
    if "inruil" in raw or "taxatie" in raw:
        return VehicleStatus.INRUIL
    if "voorbereiding" in raw or "prep" in raw:
        return VehicleStatus.IN_VOORBEREIDING
    if "klaar" in raw or "verkoop" in raw and "klaar" in raw:
        return VehicleStatus.KLAAR_VOOR_VERKOOP
    if "verkocht" in raw:
        return VehicleStatus.VERKOCHT
    return VehicleStatus.INGEKOCHT


def _map_gaston_appointment_type(raw: Optional[str]) -> AppointmentType:
    if not raw:
        return AppointmentType.OVERIG
    raw = raw.lower()
    if "onderhoud" in raw:
        return AppointmentType.ONDERHOUD
    if "reparatie" in raw:
        return AppointmentType.REPARATIE
    if "apk" in raw:
        return AppointmentType.APK
    if "verkoop" in raw:
        return AppointmentType.VERKOOP
    if "inruil" in raw or "taxatie" in raw:
        return AppointmentType.INRUIL_TAXATIE
    if "levering" in raw:
        return AppointmentType.LEVERING
    return AppointmentType.OVERIG


# ──────────────────────────────────────────────────────────
# Klantsynchronisatie
# ──────────────────────────────────────────────────────────

async def _upsert_customer_from_gaston(db: AsyncSession, raw: GastonCustomer) -> Customer:
    result = await db.execute(select(Customer).where(Customer.gaston_id == raw.gaston_id))
    customer = result.scalar_one_or_none()

    if not customer:
        customer = Customer(gaston_id=raw.gaston_id)
        db.add(customer)

    customer.first_name = raw.first_name or customer.first_name
    customer.last_name = raw.last_name or customer.last_name
    customer.company_name = raw.company_name or customer.company_name
    customer.email = raw.email or customer.email
    customer.phone = raw.phone or customer.phone
    customer.street = raw.street or customer.street
    customer.postal_code = raw.postal_code or customer.postal_code
    customer.city = raw.city or customer.city
    customer.is_business = raw.is_business

    await db.flush()
    return customer


async def _upsert_customer_from_sam(db: AsyncSession, raw: SamCustomer) -> Customer:
    result = await db.execute(select(Customer).where(Customer.sam_id == raw.sam_id))
    customer = result.scalar_one_or_none()

    if not customer:
        # Probeer ook te matchen op email
        if raw.email:
            result2 = await db.execute(select(Customer).where(Customer.email == raw.email))
            customer = result2.scalar_one_or_none()

    if not customer:
        customer = Customer(sam_id=raw.sam_id)
        db.add(customer)
    else:
        customer.sam_id = raw.sam_id

    customer.first_name = raw.first_name or customer.first_name
    customer.last_name = raw.last_name or customer.last_name
    customer.company_name = raw.company_name or customer.company_name
    customer.email = raw.email or customer.email
    customer.phone = raw.phone or customer.phone
    customer.mobile = raw.mobile or customer.mobile
    customer.street = raw.street or customer.street
    customer.house_number = raw.house_number or customer.house_number
    customer.postal_code = raw.postal_code or customer.postal_code
    customer.city = raw.city or customer.city
    customer.is_business = raw.is_business

    await db.flush()
    return customer


# ──────────────────────────────────────────────────────────
# Voertuigsynchronisatie
# ──────────────────────────────────────────────────────────

async def _upsert_vehicle_from_sam(db: AsyncSession, raw: SamVehicle) -> Vehicle:
    result = await db.execute(select(Vehicle).where(Vehicle.sam_id == raw.sam_id))
    vehicle = result.scalar_one_or_none()

    is_new = vehicle is None
    if is_new:
        # Probeer ook te matchen op kenteken of VIN
        if raw.license_plate:
            r2 = await db.execute(select(Vehicle).where(Vehicle.license_plate == raw.license_plate))
            vehicle = r2.scalar_one_or_none()
        if not vehicle and raw.vin:
            r3 = await db.execute(select(Vehicle).where(Vehicle.vin == raw.vin))
            vehicle = r3.scalar_one_or_none()

    if not vehicle:
        vehicle = Vehicle(sam_id=raw.sam_id)
        db.add(vehicle)
        is_new = True
    else:
        vehicle.sam_id = raw.sam_id

    old_status = vehicle.status

    vehicle.license_plate = raw.license_plate or vehicle.license_plate
    vehicle.vin = raw.vin or vehicle.vin
    vehicle.make = raw.make or vehicle.make
    vehicle.model = raw.model or vehicle.model
    vehicle.year = raw.year or vehicle.year
    vehicle.mileage = raw.mileage or vehicle.mileage
    vehicle.color = raw.color or vehicle.color
    vehicle.fuel_type = raw.fuel_type or vehicle.fuel_type
    vehicle.purchase_price = raw.purchase_price or vehicle.purchase_price
    vehicle.trade_in_value = raw.trade_in_value or vehicle.trade_in_value
    vehicle.asking_price = raw.asking_price or vehicle.asking_price
    vehicle.sale_price = raw.sale_price or vehicle.sale_price
    vehicle.is_trade_in = raw.is_trade_in
    vehicle.status = _map_sam_vehicle_status(raw.status)

    await db.flush()

    # Maak automatisch een checklist aan bij nieuw ingekocht voertuig
    if is_new and vehicle.status == VehicleStatus.INGEKOCHT:
        await create_vehicle_checklist(db, vehicle, "inkoop_controle")

    # Signaleer als voertuig klaar is voor verkoop
    if old_status != VehicleStatus.KLAAR_VOOR_VERKOOP and vehicle.status == VehicleStatus.KLAAR_VOOR_VERKOOP:
        notif = Notification(
            notification_type=NotificationType.VOERTUIG_KLAAR,
            priority=NotificationPriority.NORMAAL,
            title=f"Voertuig klaar voor verkoop",
            message=f"{vehicle.make} {vehicle.model} ({vehicle.license_plate}) is klaar voor verkoop.",
            vehicle_id=vehicle.id,
        )
        db.add(notif)

    return vehicle


async def _upsert_vehicle_from_vwe(db: AsyncSession, raw: VweVehicle) -> Vehicle:
    """
    Voertuig upsert vanuit VWE advertentiedata.

    Volgorde van matching (meest specifiek naar minst):
    1. vwe_id (= advertentie-ID)
    2. kenteken
    3. VIN
    """
    result = await db.execute(select(Vehicle).where(Vehicle.vwe_id == raw.vwe_id))
    vehicle = result.scalar_one_or_none()

    if not vehicle and raw.license_plate:
        lp_clean = re.sub(r"[^A-Z0-9]", "", raw.license_plate.upper())
        r2 = await db.execute(select(Vehicle).where(Vehicle.license_plate == lp_clean))
        vehicle = r2.scalar_one_or_none()

    if not vehicle and raw.vin:
        r3 = await db.execute(select(Vehicle).where(Vehicle.vin == raw.vin))
        vehicle = r3.scalar_one_or_none()

    is_new = vehicle is None
    if is_new:
        vehicle = Vehicle(vwe_id=raw.vwe_id)
        db.add(vehicle)
    else:
        vehicle.vwe_id = raw.vwe_id

    # Kenteken normaliseren (VWE geeft soms "XX-123-Y", soms "XX123Y")
    if raw.license_plate:
        vehicle.license_plate = re.sub(r"[^A-Z0-9]", "", raw.license_plate.upper()) or vehicle.license_plate

    vehicle.vin = raw.vin or vehicle.vin
    vehicle.make = raw.make or vehicle.make
    vehicle.model = raw.model or vehicle.model
    vehicle.year = raw.year or vehicle.year
    vehicle.mileage = raw.mileage or vehicle.mileage
    vehicle.color = raw.color or vehicle.color
    vehicle.fuel_type = raw.fuel_type or vehicle.fuel_type
    vehicle.apk_expiry = raw.apk_expiry or vehicle.apk_expiry
    vehicle.asking_price = raw.asking_price or vehicle.asking_price

    # Status: als VWE "Verlopen" meldt → voertuig is waarschijnlijk verkocht
    if raw.status:
        status_lower = raw.status.lower()
        if "verlopen" in status_lower or "verkocht" in status_lower:
            vehicle.status = VehicleStatus.VERKOCHT
        elif "actief" in status_lower and vehicle.status == VehicleStatus.INGEKOCHT:
            vehicle.status = VehicleStatus.KLAAR_VOOR_VERKOOP

    # APK-waarschuwing bij bijna verlopen
    if raw.apk_expiry:
        from datetime import date, timedelta
        today = date.today()
        if raw.apk_expiry < today + timedelta(days=30):
            notif = Notification(
                notification_type=NotificationType.APK_BIJNA_VERLOPEN,
                priority=NotificationPriority.HOOG,
                title=f"APK bijna verlopen — {raw.license_plate}",
                message=(
                    f"VWE meldt: APK van {raw.make or ''} {raw.model or ''} "
                    f"({raw.license_plate}) verloopt op {raw.apk_expiry}."
                ),
                vehicle_id=vehicle.id if vehicle.id else None,
            )
            db.add(notif)

    await db.flush()
    return vehicle


# ──────────────────────────────────────────────────────────
# Werkorder- en afsprakensynchronisatie
# ──────────────────────────────────────────────────────────

async def _upsert_work_order_from_gaston(db: AsyncSession, raw: GastonWorkOrder) -> Optional[WorkOrder]:
    result = await db.execute(select(WorkOrder).where(WorkOrder.gaston_id == raw.gaston_id))
    wo = result.scalar_one_or_none()

    # Zoek het voertuig op kenteken
    vehicle = None
    if raw.license_plate:
        rv = await db.execute(select(Vehicle).where(Vehicle.license_plate == raw.license_plate))
        vehicle = rv.scalar_one_or_none()

    if not vehicle:
        logger.warning(f"Gaston werkorder {raw.gaston_id}: voertuig niet gevonden voor kenteken {raw.license_plate}")
        return None

    if not wo:
        wo = WorkOrder(gaston_id=raw.gaston_id, order_number=raw.order_number, vehicle_id=vehicle.id)
        db.add(wo)

    old_status = wo.status

    wo.vehicle_id = vehicle.id
    wo.order_type = _map_gaston_order_type(raw.order_type)
    wo.status = _map_gaston_order_status(raw.status)
    wo.description = raw.description or wo.description
    wo.mechanic = raw.mechanic or wo.mechanic
    wo.planned_date = raw.planned_date or wo.planned_date
    wo.completed_at = raw.completed_date or wo.completed_at
    wo.parts_cost = raw.parts_cost or wo.parts_cost
    wo.labour_cost = raw.labour_cost or wo.labour_cost

    await db.flush()

    # Signaleer statuswijziging
    if old_status and old_status != wo.status:
        notif = Notification(
            notification_type=NotificationType.WERKORDER_STATUS,
            priority=NotificationPriority.NORMAAL,
            title=f"Werkorder {wo.order_number} status gewijzigd",
            message=f"Werkorder {wo.order_number} is nu: {wo.status.value}",
            vehicle_id=vehicle.id,
            work_order_id=wo.id,
        )
        db.add(notif)

    return wo


async def _upsert_appointment_from_gaston(db: AsyncSession, raw: GastonAppointment) -> Optional[Appointment]:
    if not raw.start_time or not raw.end_time:
        return None

    result = await db.execute(select(Appointment).where(Appointment.gaston_id == raw.gaston_id))
    appt = result.scalar_one_or_none()

    vehicle = None
    if raw.license_plate:
        rv = await db.execute(select(Vehicle).where(Vehicle.license_plate == raw.license_plate))
        vehicle = rv.scalar_one_or_none()

    if not appt:
        appt = Appointment(
            gaston_id=raw.gaston_id,
            appointment_type=_map_gaston_appointment_type(raw.appointment_type),
            start_time=raw.start_time,
            end_time=raw.end_time,
        )
        db.add(appt)

    if vehicle:
        appt.vehicle_id = vehicle.id

    appt.appointment_type = _map_gaston_appointment_type(raw.appointment_type)
    appt.start_time = raw.start_time
    appt.end_time = raw.end_time
    appt.mechanic = raw.mechanic or appt.mechanic
    appt.notes = raw.notes or appt.notes
    appt.status = AppointmentStatus.GEPLAND

    await db.flush()
    return appt


# ──────────────────────────────────────────────────────────
# Hoofd sync-taken
# ──────────────────────────────────────────────────────────

async def sync_gaston(db: AsyncSession) -> SyncLog:
    log = SyncLog(
        source=SyncSource.GASTON,
        status=SyncStatus.GESTART,
        started_at=_now(),
    )
    db.add(log)
    await db.flush()

    connector = GastonConnector()
    created = updated = failed = 0

    try:
        # Klanten
        for raw_customer in connector.fetch_customers():
            try:
                await _upsert_customer_from_gaston(db, raw_customer)
                created += 1
            except Exception as e:
                logger.error(f"Gaston klant {raw_customer.gaston_id}: {e}")
                failed += 1

        # Werkorders
        for raw_wo in connector.fetch_work_orders():
            try:
                result = await _upsert_work_order_from_gaston(db, raw_wo)
                if result:
                    created += 1
            except Exception as e:
                logger.error(f"Gaston werkorder {raw_wo.gaston_id}: {e}")
                failed += 1

        # Afspraken
        for raw_appt in connector.fetch_appointments():
            try:
                result = await _upsert_appointment_from_gaston(db, raw_appt)
                if result:
                    created += 1
            except Exception as e:
                logger.error(f"Gaston afspraak {raw_appt.gaston_id}: {e}")
                failed += 1

        log.status = SyncStatus.SUCCES if failed == 0 else SyncStatus.GEDEELTELIJK

    except Exception as e:
        log.status = SyncStatus.FOUT
        log.error_message = str(e)
        logger.error(f"Gaston sync mislukt: {e}")

    log.finished_at = _now()
    log.records_created = created
    log.records_failed = failed
    await db.flush()
    logger.info(f"Gaston sync klaar: {created} verwerkt, {failed} mislukt")
    return log


async def sync_sam(db: AsyncSession) -> SyncLog:
    log = SyncLog(
        source=SyncSource.SAM,
        status=SyncStatus.GESTART,
        started_at=_now(),
    )
    db.add(log)
    await db.flush()

    connector = SamConnector()
    created = failed = 0

    try:
        for raw_customer in connector.fetch_customers():
            try:
                await _upsert_customer_from_sam(db, raw_customer)
                created += 1
            except Exception as e:
                logger.error(f"SAM klant {raw_customer.sam_id}: {e}")
                failed += 1

        for raw_vehicle in connector.fetch_vehicles():
            try:
                await _upsert_vehicle_from_sam(db, raw_vehicle)
                created += 1
            except Exception as e:
                logger.error(f"SAM voertuig {raw_vehicle.sam_id}: {e}")
                failed += 1

        log.status = SyncStatus.SUCCES if failed == 0 else SyncStatus.GEDEELTELIJK

    except Exception as e:
        log.status = SyncStatus.FOUT
        log.error_message = str(e)
        logger.error(f"SAM sync mislukt: {e}")

    log.finished_at = _now()
    log.records_created = created
    log.records_failed = failed
    await db.flush()
    logger.info(f"SAM sync klaar: {created} verwerkt, {failed} mislukt")
    return log


async def sync_vwe(db: AsyncSession) -> SyncLog:
    """
    Synchroniseert alle actieve VWE-advertenties naar de centrale database.

    Gebruikt VweConnector.sync_all_vehicles() die:
    1. De advertentielijst ophaalt via de Angular scope van /services/adv/list
    2. Per advertentie de vehicleinfo-pagina opent en velden leest
    3. De aangevinkte opties ophaalt van de accessories-pagina
    """
    log = SyncLog(
        source=SyncSource.VWE,
        status=SyncStatus.GESTART,
        started_at=_now(),
    )
    db.add(log)
    await db.flush()

    created = failed = 0

    try:
        async with VweConnector() as vwe:
            if not await vwe.login():
                raise RuntimeError("VWE login mislukt — controleer VWE_USERNAME/VWE_PASSWORD in .env")

            vehicles = await vwe.sync_all_vehicles()

            for raw_vehicle in vehicles:
                try:
                    await _upsert_vehicle_from_vwe(db, raw_vehicle)
                    created += 1
                except Exception as e:
                    logger.error(f"VWE voertuig {raw_vehicle.vwe_id}: {e}")
                    failed += 1

        log.status = SyncStatus.SUCCES if failed == 0 else SyncStatus.GEDEELTELIJK

    except Exception as e:
        log.status = SyncStatus.FOUT
        log.error_message = str(e)
        logger.error(f"VWE sync mislukt: {e}")

        # Notificatie aanmaken bij sync-fout
        notif = Notification(
            notification_type=NotificationType.SYNC_FOUT,
            priority=NotificationPriority.HOOG,
            title="VWE synchronisatie mislukt",
            message=f"VWE sync mislukt: {str(e)[:200]}",
        )
        db.add(notif)

    log.finished_at = _now()
    log.records_created = created
    log.records_failed = failed
    await db.flush()
    logger.info(f"VWE sync klaar: {created} verwerkt, {failed} mislukt")
    return log
