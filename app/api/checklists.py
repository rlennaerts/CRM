from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.checklist import Checklist, ChecklistItem, ChecklistType, ChecklistItemStatus
from app.tasks.checklist_factory import create_vehicle_checklist, CHECKLIST_TEMPLATES

router = APIRouter(prefix="/checklists", tags=["Checklists"])


# ──────────────────────────────────────────────────────────
# Pydantic schema's
# ──────────────────────────────────────────────────────────

class ChecklistItemOut(BaseModel):
    id: int
    order: int
    category: Optional[str]
    label: str
    is_required: bool
    status: ChecklistItemStatus
    checked_by: Optional[str]
    checked_at: Optional[datetime]
    notes: Optional[str]
    estimated_cost: Optional[float]

    class Config:
        from_attributes = True


class CategorySummary(BaseModel):
    category: str
    total: int
    ok: int
    actie_vereist: int
    afgekeurd: int
    niet_gecontroleerd: int
    completion_pct: int


class ChecklistOut(BaseModel):
    id: int
    vehicle_id: int
    checklist_type: ChecklistType
    title: str
    assigned_to: Optional[str]
    completed_at: Optional[datetime]
    completed_by: Optional[str]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    general_notes: Optional[str]
    completion_percentage: int
    has_blocking_issues: bool
    open_action_count: int
    rejected_count: int
    items: list[ChecklistItemOut]
    category_summary: list[CategorySummary]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_summary(cls, checklist: Checklist) -> "ChecklistOut":
        items_out = [ChecklistItemOut.model_validate(i) for i in checklist.items]

        # Groepeer per categorie
        cats: dict[str, dict] = {}
        for item in checklist.items:
            cat = item.category or "Overig"
            if cat not in cats:
                cats[cat] = {"total": 0, "ok": 0, "actie_vereist": 0, "afgekeurd": 0, "niet_gecontroleerd": 0}
            cats[cat]["total"] += 1
            cats[cat][item.status.value] += 1

        cat_summary = [
            CategorySummary(
                category=cat,
                total=v["total"],
                ok=v["ok"],
                actie_vereist=v["actie_vereist"],
                afgekeurd=v["afgekeurd"],
                niet_gecontroleerd=v["niet_gecontroleerd"],
                completion_pct=round((v["ok"] + v["actie_vereist"] + v["afgekeurd"]) / v["total"] * 100) if v["total"] else 0,
            )
            for cat, v in cats.items()
        ]

        return cls(
            id=checklist.id,
            vehicle_id=checklist.vehicle_id,
            checklist_type=checklist.checklist_type,
            title=checklist.title,
            assigned_to=checklist.assigned_to,
            completed_at=checklist.completed_at,
            completed_by=checklist.completed_by,
            approved_by=checklist.approved_by,
            approved_at=checklist.approved_at,
            general_notes=checklist.general_notes,
            completion_percentage=checklist.completion_percentage,
            has_blocking_issues=checklist.has_blocking_issues,
            open_action_count=checklist.open_action_count,
            rejected_count=checklist.rejected_count,
            items=items_out,
            category_summary=cat_summary,
        )


class ChecklistCreate(BaseModel):
    vehicle_id: int
    checklist_type: str
    assigned_to: Optional[str] = None
    work_order_id: Optional[int] = None


class ItemUpdate(BaseModel):
    status: ChecklistItemStatus
    checked_by: Optional[str] = None
    notes: Optional[str] = None
    estimated_cost: Optional[float] = None


class ChecklistApproval(BaseModel):
    approved_by: str
    general_notes: Optional[str] = None


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────

@router.get("/vehicle/{vehicle_id}", response_model=list[ChecklistOut])
async def get_vehicle_checklists(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Checklist).where(Checklist.vehicle_id == vehicle_id)
    )
    checklists = result.scalars().all()
    # Laad items expliciet voor ieder checklist
    for cl in checklists:
        await db.refresh(cl, ["items"])
    return [ChecklistOut.from_orm_with_summary(cl) for cl in checklists]


@router.get("/{checklist_id}", response_model=ChecklistOut)
async def get_checklist(checklist_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist niet gevonden")
    await db.refresh(checklist, ["items"])
    return ChecklistOut.from_orm_with_summary(checklist)


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
    await db.refresh(checklist, ["items"])
    return ChecklistOut.from_orm_with_summary(checklist)


@router.patch("/{checklist_id}/items/{item_id}", response_model=ChecklistItemOut)
async def update_item(
    checklist_id: int,
    item_id: int,
    body: ItemUpdate,
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

    item.status = body.status
    item.checked_by = body.checked_by
    item.estimated_cost = body.estimated_cost
    if body.notes is not None:
        item.notes = body.notes
    if body.status != ChecklistItemStatus.NIET_GECONTROLEERD:
        item.checked_at = datetime.now(tz=timezone.utc)
    else:
        item.checked_at = None

    # Controleer of de checklist nu volledig ingevuld is
    cl_result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
    checklist = cl_result.scalar_one()
    await db.refresh(checklist, ["items"])

    all_required_done = all(
        i.status != ChecklistItemStatus.NIET_GECONTROLEERD
        for i in checklist.items
        if i.is_required
    )
    if all_required_done and not checklist.completed_at:
        checklist.completed_at = datetime.now(tz=timezone.utc)
        checklist.completed_by = body.checked_by

    await db.flush()
    return item


@router.post("/{checklist_id}/approve")
async def approve_checklist(
    checklist_id: int,
    body: ChecklistApproval,
    db: AsyncSession = Depends(get_db),
):
    """
    Goedkeuring door technisch verantwoordelijke.
    Alleen mogelijk als er geen AFGEKEURDE items zijn.
    """
    result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist niet gevonden")

    await db.refresh(checklist, ["items"])

    if checklist.has_blocking_issues:
        blocking = [i.label for i in checklist.items if i.status == ChecklistItemStatus.AFGEKEURD]
        raise HTTPException(
            status_code=422,
            detail=f"Kan niet goedkeuren: {len(blocking)} afgekeurde punt(en): {blocking[:3]}{'...' if len(blocking) > 3 else ''}",
        )

    checklist.approved_by = body.approved_by
    checklist.approved_at = datetime.now(tz=timezone.utc)
    if body.general_notes:
        checklist.general_notes = body.general_notes

    await db.flush()
    return {"ok": True, "approved_by": body.approved_by, "approved_at": checklist.approved_at}


@router.get("/{checklist_id}/rapport")
async def get_rapport(checklist_id: int, db: AsyncSession = Depends(get_db)):
    """
    Exporteerbaar keuringsrapport met alle bevindingen, actie-items en kosten.
    """
    result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist niet gevonden")

    await db.refresh(checklist, ["items", "vehicle"])

    v = checklist.vehicle
    vehicle_desc = f"{v.make or ''} {v.model or ''} ({v.license_plate or '—'})".strip()

    # Groepeer items per categorie
    by_category: dict[str, list] = {}
    total_estimated_cost = 0.0
    for item in checklist.items:
        cat = item.category or "Overig"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "label": item.label,
            "status": item.status.value,
            "required": item.is_required,
            "checked_by": item.checked_by,
            "notes": item.notes,
            "estimated_cost": item.estimated_cost,
        })
        if item.estimated_cost:
            total_estimated_cost += item.estimated_cost

    action_items = [
        {"category": item.category, "label": item.label, "notes": item.notes, "estimated_cost": item.estimated_cost}
        for item in checklist.items
        if item.status == ChecklistItemStatus.ACTIE_VEREIST
    ]
    rejected_items = [
        {"category": item.category, "label": item.label, "notes": item.notes, "estimated_cost": item.estimated_cost}
        for item in checklist.items
        if item.status == ChecklistItemStatus.AFGEKEURD
    ]

    return {
        "rapport": {
            "checklist_id": checklist.id,
            "type": checklist.checklist_type.value,
            "title": checklist.title,
            "voertuig": vehicle_desc,
            "kenteken": v.license_plate,
            "vin": v.vin,
            "km_stand": v.mileage,
            "assigned_to": checklist.assigned_to,
            "aangemaakt_op": checklist.created_at,
            "afgerond_op": checklist.completed_at,
            "goedgekeurd_door": checklist.approved_by,
            "goedgekeurd_op": checklist.approved_at,
            "algemene_opmerkingen": checklist.general_notes,
        },
        "samenvatting": {
            "totaal_punten": len(checklist.items),
            "goedgekeurd": sum(1 for i in checklist.items if i.status == ChecklistItemStatus.OK),
            "actie_vereist": len(action_items),
            "afgekeurd": len(rejected_items),
            "niet_gecontroleerd": sum(1 for i in checklist.items if i.status == ChecklistItemStatus.NIET_GECONTROLEERD),
            "voortgang_pct": checklist.completion_percentage,
            "totaal_geschatte_kosten": round(total_estimated_cost, 2),
        },
        "actie_items": action_items,
        "afgekeurde_punten": rejected_items,
        "bevindingen_per_sectie": by_category,
    }


@router.get("/templates")
async def get_templates(detailed: bool = Query(False)):
    """Geef beschikbare checklist-templates terug."""
    if detailed:
        return {
            key: {
                "total_items": len(items),
                "required_items": sum(1 for i in items if i["required"]),
                "categories": sorted(set(i.get("category", "Overig") for i in items)),
                "items": items,
            }
            for key, items in CHECKLIST_TEMPLATES.items()
        }
    return {
        key: {
            "total_items": len(items),
            "required_items": sum(1 for i in items if i["required"]),
            "categories": sorted(set(i.get("category", "Overig") for i in items)),
        }
        for key, items in CHECKLIST_TEMPLATES.items()
    }
