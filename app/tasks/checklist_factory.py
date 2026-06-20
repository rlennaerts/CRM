"""
Maakt automatisch checklists aan voor voertuigen op basis van type/status.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist import Checklist, ChecklistItem, ChecklistType
from app.models.vehicle import Vehicle


CHECKLIST_TEMPLATES: dict[str, list[dict]] = {
    "inkoop_controle": [
        {"label": "Kenteken geregistreerd in systeem", "required": True},
        {"label": "VIN gecontroleerd en geregistreerd", "required": True},
        {"label": "Kilometerstand genoteerd", "required": True},
        {"label": "Schade-inspectie uitgevoerd en gefotografeerd", "required": True},
        {"label": "Banden gecontroleerd (profiel + spanning)", "required": True},
        {"label": "Remmen gecontroleerd", "required": True},
        {"label": "Oliepeil gecontroleerd", "required": True},
        {"label": "Koelvloeistof gecontroleerd", "required": False},
        {"label": "Ruitenwisservloeistof gecontroleerd", "required": False},
        {"label": "Accu getest", "required": True},
        {"label": "Airco getest", "required": False},
        {"label": "Verwarming getest", "required": False},
        {"label": "Alle lichten gecontroleerd", "required": True},
        {"label": "Sleutels aanwezig (aantal)", "required": True},
        {"label": "Kentekenbewijs aanwezig", "required": True},
        {"label": "APK-datum gecontroleerd", "required": True},
        {"label": "Onderhoudsboekje aanwezig/gecontroleerd", "required": False},
    ],
    "voorbereiding": [
        {"label": "Voertuig inwendig gereinigd", "required": True},
        {"label": "Voertuig uitwendig gewassen en gepolijst", "required": True},
        {"label": "Ramen gereinigd", "required": True},
        {"label": "Velgen gereinigd", "required": True},
        {"label": "Onderhoud uitgevoerd (olie/filter)", "required": True},
        {"label": "APK aangevraagd / in orde", "required": True},
        {"label": "Schadereparatie afgerond", "required": False},
        {"label": "Carrosserie-herstel afgerond", "required": False},
        {"label": "Technische keuring intern uitgevoerd", "required": True},
        {"label": "Navigatie/software bijgewerkt", "required": False},
        {"label": "Bandenspanning ingesteld", "required": True},
        {"label": "Ruitenwisserbladen gecontroleerd/vervangen", "required": False},
        {"label": "Fotografie voor advertentie gemaakt", "required": True},
        {"label": "Advertentietekst gemaakt", "required": True},
        {"label": "Prijs vastgesteld en ingevoerd in systeem", "required": True},
    ],
    "aflevercheck": [
        {"label": "Voertuig schoon (binnen en buiten)", "required": True},
        {"label": "Tanken / afgesproken brandstofniveau", "required": True},
        {"label": "Kentekenbewijs op naam klant", "required": True},
        {"label": "Verzekering klant actief", "required": True},
        {"label": "Alle sleutels overhandigd", "required": True},
        {"label": "Onderhoudsboekje / garantiebewijs overhandigd", "required": False},
        {"label": "NAP-rapport overhandigd", "required": True},
        {"label": "Klant rondgeleid door voertuig", "required": True},
        {"label": "Klanthandtekening op afleverbon", "required": True},
        {"label": "Betaling ontvangen / financiering afgerond", "required": True},
        {"label": "Navigatie geprogrammeerd op klantadres", "required": False},
        {"label": "Bijzonderheden klant besproken", "required": False},
    ],
    "inruil_taxatie": [
        {"label": "Kenteken en VIN gecontroleerd", "required": True},
        {"label": "Kilometerstand genoteerd", "required": True},
        {"label": "NAP-controle uitgevoerd", "required": True},
        {"label": "Schade-inventarisatie gemaakt", "required": True},
        {"label": "Foto's gemaakt van schade", "required": True},
        {"label": "Technische staat beoordeeld", "required": True},
        {"label": "APK-datum genoteerd", "required": True},
        {"label": "Taxatiewaarde bepaald", "required": True},
        {"label": "Taxatierapport opgemaakt", "required": True},
        {"label": "Klant geïnformeerd over taxatiewaarde", "required": True},
    ],
}


async def create_vehicle_checklist(
    db: AsyncSession,
    vehicle: Vehicle,
    checklist_type_str: str,
    assigned_to: str = None,
    work_order_id: int = None,
) -> Checklist:
    """Maak een nieuwe checklist aan voor een voertuig."""

    type_map = {
        "inkoop_controle": ChecklistType.INKOOP_CONTROLE,
        "voorbereiding": ChecklistType.VOORBEREIDING,
        "aflevercheck": ChecklistType.AFLEVERCHECK,
        "apk_voorbereiding": ChecklistType.APK_VOORBEREIDING,
        "inruil_taxatie": ChecklistType.INRUIL_TAXATIE,
    }

    checklist_type = type_map.get(checklist_type_str, ChecklistType.VOORBEREIDING)
    template = CHECKLIST_TEMPLATES.get(checklist_type_str, [])

    title_map = {
        ChecklistType.INKOOP_CONTROLE: "Inkoop-controle",
        ChecklistType.VOORBEREIDING: "Voorbereiding voor verkoop",
        ChecklistType.AFLEVERCHECK: "Aflevercheck",
        ChecklistType.APK_VOORBEREIDING: "APK-voorbereiding",
        ChecklistType.INRUIL_TAXATIE: "Inruil / taxatie",
    }

    vehicle_desc = f"{vehicle.make or ''} {vehicle.model or ''} ({vehicle.license_plate or 'geen kenteken'})".strip()
    title = f"{title_map[checklist_type]} — {vehicle_desc}"

    checklist = Checklist(
        vehicle_id=vehicle.id,
        work_order_id=work_order_id,
        checklist_type=checklist_type,
        title=title,
        assigned_to=assigned_to,
    )
    db.add(checklist)
    await db.flush()

    for i, item_def in enumerate(template):
        item = ChecklistItem(
            checklist_id=checklist.id,
            order=i,
            label=item_def["label"],
            is_required=item_def["required"],
        )
        db.add(item)

    await db.flush()
    return checklist
