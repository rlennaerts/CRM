from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, Boolean
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class AppointmentType(str, enum.Enum):
    ONDERHOUD = "onderhoud"
    REPARATIE = "reparatie"
    APK = "apk"
    VERKOOP = "verkoop"
    INRUIL_TAXATIE = "inruil_taxatie"
    LEVERING = "levering"
    OVERIG = "overig"


class AppointmentStatus(str, enum.Enum):
    GEPLAND = "gepland"
    BEVESTIGD = "bevestigd"
    GEANNULEERD = "geannuleerd"
    AFGEROND = "afgerond"
    NO_SHOW = "no_show"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)

    gaston_id = Column(String(64), nullable=True, index=True)
    sam_id = Column(String(64), nullable=True, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer")

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    vehicle = relationship("Vehicle")

    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    work_order = relationship("WorkOrder")

    appointment_type = Column(Enum(AppointmentType), nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.GEPLAND)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    mechanic = Column(String(128), nullable=True)
    location = Column(String(128), nullable=True)  # bijv. werkplaatsbay

    notes = Column(Text, nullable=True)
    customer_notified = Column(Boolean, default=False)
    reminder_sent = Column(Boolean, default=False)
