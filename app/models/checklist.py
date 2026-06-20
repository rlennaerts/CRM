from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, Text, DateTime
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class ChecklistType(str, enum.Enum):
    INKOOP_CONTROLE = "inkoop_controle"       # Bij aankoop voertuig
    VOORBEREIDING = "voorbereiding"            # Prep voor verkoop
    AFLEVERCHECK = "aflevercheck"              # Controle voor levering aan klant
    APK_VOORBEREIDING = "apk_voorbereiding"
    INRUIL_TAXATIE = "inruil_taxatie"


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

    items = relationship("ChecklistItem", back_populates="checklist", cascade="all, delete-orphan")

    @property
    def is_complete(self):
        return all(item.is_checked for item in self.items if item.is_required)

    @property
    def completion_percentage(self):
        if not self.items:
            return 0
        checked = sum(1 for i in self.items if i.is_checked)
        return round(checked / len(self.items) * 100)


class ChecklistItem(Base, TimestampMixin):
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False)
    checklist = relationship("Checklist", back_populates="items")

    order = Column(Integer, default=0)
    label = Column(String(512), nullable=False)
    is_required = Column(Boolean, default=True)
    is_checked = Column(Boolean, default=False)
    checked_by = Column(String(128), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
