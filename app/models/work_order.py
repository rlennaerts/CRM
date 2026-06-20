from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text, Boolean
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class WorkOrderStatus(str, enum.Enum):
    AANGEMELD = "aangemeld"
    INGEPLAND = "ingepland"
    IN_UITVOERING = "in_uitvoering"
    WACHT_OP_ONDERDELEN = "wacht_op_onderdelen"
    GEREED = "gereed"
    GEFACTUREERD = "gefactureerd"
    GEANNULEERD = "geannuleerd"


class WorkOrderType(str, enum.Enum):
    REPARATIE = "reparatie"
    ONDERHOUD = "onderhoud"
    VOORBEREIDING = "voorbereiding"   # Prep voor verkoop
    APK = "apk"
    GARANTIE = "garantie"
    SCHADE = "schade"


class WorkOrder(Base, TimestampMixin):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)

    # Externe systeem-IDs
    gaston_id = Column(String(64), nullable=True, index=True)
    sam_id = Column(String(64), nullable=True, index=True)

    order_number = Column(String(32), unique=True, nullable=False, index=True)

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    vehicle = relationship("Vehicle")

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer")

    order_type = Column(Enum(WorkOrderType), nullable=False)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.AANGEMELD, nullable=False)

    description = Column(Text, nullable=True)
    mechanic = Column(String(128), nullable=True)

    planned_date = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    estimated_hours = Column(Float, nullable=True)
    actual_hours = Column(Float, nullable=True)
    parts_cost = Column(Float, nullable=True)
    labour_cost = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    requires_customer_approval = Column(Boolean, default=False)
    customer_approved = Column(Boolean, nullable=True)
