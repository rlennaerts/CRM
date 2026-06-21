from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, Text, DateTime, Float
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class ChecklistType(str, enum.Enum):
    INKOOP_CONTROLE = "inkoop_controle"
    VOORBEREIDING = "voorbereiding"
    AFLEVERCHECK = "aflevercheck"
    APK_VOORBEREIDING = "apk_voorbereiding"
    INRUIL_TAXATIE = "inruil_taxatie"
    TECHNISCHE_KEURING = "technische_keuring"
    COSMETISCHE_KEURING = "cosmetische_keuring"
    RIJKLAAR_MAKEN = "rijklaar_maken"          # Gecombineerd: technisch + cosmetisch


class ChecklistItemStatus(str, enum.Enum):
    NIET_GECONTROLEERD = "niet_gecontroleerd"
    OK = "ok"
    ACTIE_VEREIST = "actie_vereist"            # Punt vereist actie maar blokkeert niet
    AFGEKEURD = "afgekeurd"                    # Blokkerende bevinding


class Checklist(Base, TimestampMixin):
    __tablename__ = "checklists"

    id = Column(Integer, primary_key=True, index=True)

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    vehicle = relationship("Vehicle")

    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    work_order = relationship("WorkOrder")

    checklist_type = Column(Enum(ChecklistType), nullable=False)
    title = Column(String(256), nullable=False)
    assigned_to = Column(String(128), nullable=True)

    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(128), nullable=True)

    # Rapportage-velden voor rijklaar/keuring checklists
    general_notes = Column(Text, nullable=True)
    approved_by = Column(String(128), nullable=True)   # Technisch verantwoordelijke
    approved_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "ChecklistItem",
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ChecklistItem.order",
    )

    @property
    def is_complete(self):
        return all(item.is_required is False or item.status != ChecklistItemStatus.NIET_GECONTROLEERD for item in self.items)

    @property
    def has_blocking_issues(self):
        return any(item.status == ChecklistItemStatus.AFGEKEURD for item in self.items)

    @property
    def completion_percentage(self):
        if not self.items:
            return 0
        done = sum(1 for i in self.items if i.status != ChecklistItemStatus.NIET_GECONTROLEERD)
        return round(done / len(self.items) * 100)

    @property
    def open_action_count(self):
        return sum(1 for i in self.items if i.status == ChecklistItemStatus.ACTIE_VEREIST)

    @property
    def rejected_count(self):
        return sum(1 for i in self.items if i.status == ChecklistItemStatus.AFGEKEURD)


class ChecklistItem(Base, TimestampMixin):
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    checklist = relationship("Checklist", back_populates="items")

    order = Column(Integer, default=0)
    category = Column(String(128), nullable=True)      # Sectie-indeling, bijv. "Motor", "Carrosserie"
    label = Column(String(512), nullable=False)
    is_required = Column(Boolean, default=True)

    # Uitgebreid statusmodel (vervangt simpele is_checked boolean)
    status = Column(
        Enum(ChecklistItemStatus),
        default=ChecklistItemStatus.NIET_GECONTROLEERD,
        nullable=False,
    )
    # Achterwaartse compatibiliteit
    @property
    def is_checked(self):
        return self.status == ChecklistItemStatus.OK

    checked_by = Column(String(128), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)                # Toelichting / bevinding
    estimated_cost = Column(Float, nullable=True)      # Geschatte reparatiekosten bij ACTIE/AFGEKEURD
