"""Generieke backend voor de Sales Portal.

Spiegelt de `StorageAdapter`-interface van de portal:
  GET    /api/portal/{collection}          → lijst
  GET    /api/portal/{collection}/{key}    → één record
  PUT    /api/portal/{collection}/{key}    → upsert
  DELETE /api/portal/{collection}/{key}    → verwijderen
  PUT    /api/portal/{collection}          → bulk-vervang collectie

Plus een brug die de echte voertuigen (VWE/Gaston/SAM) naar het
auto-model van de portal omzet:
  POST   /api/portal/_import/vehicles      → vul de 'cars'-collectie
"""
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portal_record import PortalRecord
from app.models.vehicle import Vehicle, VehicleStatus

router = APIRouter(prefix="/portal", tags=["Sales Portal"])


# ─── CRUD op collecties ────────────────────────────────────────────────────
@router.get("/{collection}")
async def list_records(collection: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PortalRecord).where(PortalRecord.collection == collection)
    )
    return [r.data for r in result.scalars().all()]


@router.get("/{collection}/{key}")
async def get_record(collection: str, key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PortalRecord).where(
            PortalRecord.collection == collection, PortalRecord.key == key
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record niet gevonden")
    return record.data


async def _upsert(db: AsyncSession, collection: str, key: str, data: dict) -> dict:
    result = await db.execute(
        select(PortalRecord).where(
            PortalRecord.collection == collection, PortalRecord.key == key
        )
    )
    record = result.scalar_one_or_none()
    if record:
        record.data = data
    else:
        db.add(PortalRecord(collection=collection, key=key, data=data))
    await db.flush()
    return data


@router.put("/{collection}/{key}")
async def put_record(
    collection: str,
    key: str,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    # De entiteit-id (key) is leidend; houd 'm consistent in de payload.
    body.setdefault("id", key)
    return await _upsert(db, collection, key, body)


@router.delete("/{collection}/{key}")
async def delete_record(collection: str, key: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        delete(PortalRecord).where(
            PortalRecord.collection == collection, PortalRecord.key == key
        )
    )
    return {"ok": True}


@router.put("/{collection}")
async def bulk_put(
    collection: str,
    items: list[dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Vervang de volledige collectie door de meegegeven lijst."""
    await db.execute(
        delete(PortalRecord).where(PortalRecord.collection == collection)
    )
    for item in items:
        key = str(item.get("id"))
        if not key or key == "None":
            continue
        db.add(PortalRecord(collection=collection, key=key, data=item))
    await db.flush()
    return {"ok": True, "count": len(items)}


# ─── Brug: echte voertuigen → portal-auto's ────────────────────────────────
_STATUS_MAP = {
    VehicleStatus.KLAAR_VOOR_VERKOOP: "beschikbaar",
    VehicleStatus.VERKOCHT: "verkocht",
    VehicleStatus.IN_VOORBEREIDING: "gereserveerd",
    VehicleStatus.INGEKOCHT: "gereserveerd",
    VehicleStatus.INRUIL: "gereserveerd",
    VehicleStatus.TAXATIE: "gereserveerd",
}


def vehicle_to_car(v: Vehicle) -> dict:
    price = v.asking_price or v.sale_price or v.purchase_price or 0
    return {
        "id": f"veh-{v.id}",
        "licensePlate": v.license_plate or "",
        "brand": v.make or "Onbekend",
        "model": v.model or "",
        "variant": v.variant or "",
        "year": v.year or 0,
        "price": float(price),
        "mileage": v.mileage or 0,
        "fuel": v.fuel_type or "",
        "transmission": v.transmission or "",
        "color": v.color or "",
        "image": "",
        "status": _STATUS_MAP.get(v.status, "beschikbaar"),
        "location": "",
        "features": [],
        "description": v.notes or "",
        "createdAt": v.created_at.isoformat() if v.created_at else "",
    }


@router.post("/_import/vehicles")
async def import_vehicles(db: AsyncSession = Depends(get_db)):
    """Zet de echte voorraad (vehicles-tabel) om naar de 'cars'-collectie."""
    result = await db.execute(select(Vehicle))
    vehicles = result.scalars().all()

    imported = 0
    for v in vehicles:
        car = vehicle_to_car(v)
        await _upsert(db, "cars", car["id"], car)
        imported += 1

    return {"ok": True, "imported": imported}
