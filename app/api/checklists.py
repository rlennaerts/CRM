from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.checklist import Checklist, ChecklistItem, ChecklistType
from app.tasks.checklist_factory import create_vehicle_checklist, CHECKLIST_TEMPLATES

router = APIRouter(prefix="/checklists", tags=["Checklists"])


class ChecklistItemOut(BaseModel):
    id: int
    order: int
    label: str
    is_required: bool
    is_checked: bool
    checked_by: Optional[str]
    checked_at: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True


class ChecklistOut(BaseModel):
    id: int
    vehicle_id: int
    checklist_type: ChecklistType
    title: str
    assigned_to: Optional[str]
    completed_at: Optional[datetime]
    completed_by: Optional[str]
    items: list[ChecklistItemOut]

    class Config:
        from_attributes = True


class ChecklistCreate(BaseModel):
    vehicle_id: int
    checklist_type: str
    assigned_to: Optional[str] = None
    work_order_id: Optional[int] = None


class ItemCheck(BaseModel):
    is_checked: bool
    checked_by: Optional[str] = None
    notes: Optional[str] = None


@router.get("/vehicle/{vehicle_id}", response_model=list[ChecklistOut])
async def get_vehicle_checklists(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Checklist).where(Checklist.vehicle_id == vehicle_id)
    )
    return result.scalars().all()


@router.post("/", response_model=ChecklistOut, status_code=201)
async def create_checklist(body: ChecklistCreate, db: AsyncSession = Depends(get_db)):
    from app.models.vehicle import Vehicle
    v_result = await db.execute(select(Vehicle).where(Vehicle.id == body.vehicle_id))
    vehicle = v_result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Voertuig niet gevonden")

    if body.checklist_type not in CHECKLIST_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Onbekend checklisttype. Kies uit: {list(CHECKLIST_TEMPLATES.keys())}",
        )

    checklist = await create_vehicle_checklist(
        db, vehicle, body.checklist_type, body.assigned_to, body.work_order_id
    )
    return checklist


@router.patch("/{checklist_id}/items/{item_id}", response_model=ChecklistItemOut)
async def check_item(
    checklist_id: int,
    item_id: int,
    body: ItemCheck,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == checklist_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item niet gevonden")

    item.is_checked = body.is_checked
    item.checked_by = body.checked_by
    item.notes = body.notes
    if body.is_checked:
        item.checked_at = datetime.now(tz=timezone.utc)
    else:
        item.checked_at = None

    # Controleer of de gehele checklist compleet is
    cl_result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
    checklist = cl_result.scalar_one()
    await db.refresh(checklist, ["items"])

    all_required_checked = all(i.is_checked for i in checklist.items if i.is_required)
    if all_required_checked and not checklist.completed_at:
        checklist.completed_at = datetime.now(tz=timezone.utc)
        checklist.completed_by = body.checked_by

    await db.flush()
    return item


@router.get("/templates")
async def get_templates():
    """Geef beschikbare checklist-templates terug."""
    return {
        key: {"items": len(items), "labels": [i["label"] for i in items]}
        for key, items in CHECKLIST_TEMPLATES.items()
    }
