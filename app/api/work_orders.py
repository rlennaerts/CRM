from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.work_order import WorkOrder, WorkOrderStatus, WorkOrderType

router = APIRouter(prefix="/work-orders", tags=["Werkorders"])


class WorkOrderOut(BaseModel):
    id: int
    order_number: str
    vehicle_id: int
    customer_id: Optional[int]
    order_type: WorkOrderType
    status: WorkOrderStatus
    description: Optional[str]
    mechanic: Optional[str]
    planned_date: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    parts_cost: Optional[float]
    labour_cost: Optional[float]
    notes: Optional[str]
    gaston_id: Optional[str]
    sam_id: Optional[str]

    class Config:
        from_attributes = True


class WorkOrderCreate(BaseModel):
    vehicle_id: int
    customer_id: Optional[int] = None
    order_type: WorkOrderType
    description: Optional[str] = None
    mechanic: Optional[str] = None
    planned_date: Optional[datetime] = None
    estimated_hours: Optional[float] = None


class WorkOrderStatusUpdate(BaseModel):
    status: WorkOrderStatus
    notes: Optional[str] = None
    actual_hours: Optional[float] = None


@router.get("/", response_model=list[WorkOrderOut])
async def list_work_orders(
    status: Optional[WorkOrderStatus] = None,
    vehicle_id: Optional[int] = None,
    mechanic: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(WorkOrder)
    if status:
        q = q.where(WorkOrder.status == status)
    if vehicle_id:
        q = q.where(WorkOrder.vehicle_id == vehicle_id)
    if mechanic:
        q = q.where(WorkOrder.mechanic.ilike(f"%{mechanic}%"))
    q = q.order_by(WorkOrder.planned_date.asc().nullslast()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=WorkOrderOut, status_code=201)
async def create_work_order(body: WorkOrderCreate, db: AsyncSession = Depends(get_db)):
    from app.models.work_order import WorkOrder
    import random, string

    order_number = "WO-" + "".join(random.choices(string.digits, k=6))
    wo = WorkOrder(
        order_number=order_number,
        vehicle_id=body.vehicle_id,
        customer_id=body.customer_id,
        order_type=body.order_type,
        status=WorkOrderStatus.AANGEMELD,
        description=body.description,
        mechanic=body.mechanic,
        planned_date=body.planned_date,
        estimated_hours=body.estimated_hours,
    )
    db.add(wo)
    await db.flush()
    return wo


@router.patch("/{wo_id}/status", response_model=WorkOrderOut)
async def update_work_order_status(
    wo_id: int,
    body: WorkOrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == wo_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="Werkorder niet gevonden")

    wo.status = body.status
    if body.notes:
        wo.notes = body.notes
    if body.actual_hours:
        wo.actual_hours = body.actual_hours
    if body.status == WorkOrderStatus.IN_UITVOERING and not wo.started_at:
        from datetime import timezone
        wo.started_at = datetime.now(tz=timezone.utc)
    if body.status == WorkOrderStatus.GEREED and not wo.completed_at:
        from datetime import timezone
        wo.completed_at = datetime.now(tz=timezone.utc)

    await db.flush()
    return wo
