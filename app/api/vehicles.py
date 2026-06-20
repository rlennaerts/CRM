from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import date

from app.database import get_db
from app.models.vehicle import Vehicle, VehicleStatus

router = APIRouter(prefix="/vehicles", tags=["Voertuigen"])


class VehicleOut(BaseModel):
    id: int
    license_plate: Optional[str]
    vin: Optional[str]
    make: Optional[str]
    model: Optional[str]
    variant: Optional[str]
    year: Optional[int]
    mileage: Optional[int]
    color: Optional[str]
    fuel_type: Optional[str]
    apk_expiry: Optional[date]
    purchase_price: Optional[float]
    trade_in_value: Optional[float]
    asking_price: Optional[float]
    sale_price: Optional[float]
    status: VehicleStatus
    is_trade_in: bool
    notes: Optional[str]
    vwe_id: Optional[str]
    gaston_id: Optional[str]
    sam_id: Optional[str]

    class Config:
        from_attributes = True


class VehicleStatusUpdate(BaseModel):
    status: VehicleStatus
    notes: Optional[str] = None


@router.get("/", response_model=list[VehicleOut])
async def list_vehicles(
    status: Optional[VehicleStatus] = None,
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(Vehicle)
    if status:
        q = q.where(Vehicle.status == status)
    if search:
        q = q.where(
            Vehicle.license_plate.ilike(f"%{search}%")
            | Vehicle.make.ilike(f"%{search}%")
            | Vehicle.model.ilike(f"%{search}%")
        )
    q = q.order_by(Vehicle.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/stats")
async def vehicle_stats(db: AsyncSession = Depends(get_db)):
    """Overzicht van voertuigaantallen per status."""
    result = await db.execute(
        select(Vehicle.status, func.count(Vehicle.id)).group_by(Vehicle.status)
    )
    return {row[0].value: row[1] for row in result.all()}


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Voertuig niet gevonden")
    return vehicle


@router.patch("/{vehicle_id}/status", response_model=VehicleOut)
async def update_vehicle_status(
    vehicle_id: int,
    body: VehicleStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Voertuig niet gevonden")

    vehicle.status = body.status
    if body.notes:
        vehicle.notes = body.notes

    await db.flush()
    return vehicle
