from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, Text, DateTime
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class NotificationType(str, enum.Enum):
    APK_VERLOPEN = "apk_verlopen"
    APK_BIJNA_VERLOPEN = "apk_bijna_verlopen"
    VOERTUIG_KLAAR = "voertuig_klaar"
    AFSPRAAK_HERINNERING = "afspraak_herinnering"
    WERKORDER_STATUS = "werkorder_status"
    INKOOP_ACTIE_VEREIST = "inkoop_actie_vereist"
    CHECKLIST_NIET_COMPLEET = "checklist_niet_compleet"
    SYNC_FOUT = "sync_fout"
    INRUIL_TAXATIE = "inruil_taxatie"


class NotificationPriority(str, enum.Enum):
    LAAG = "laag"
    NORMAAL = "normaal"
    HOOG = "hoog"
    URGENT = "urgent"


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    notification_type = Column(Enum(NotificationType), nullable=False)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.NORMAAL)

    title = Column(String(256), nullable=False)
    message = Column(Text, nullable=False)

    # Optionele links naar gerelateerde objecten
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    vehicle = relationship("Vehicle")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer")
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    work_order = relationship("WorkOrder")

    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    assigned_to = Column(String(128), nullable=True)  # Specifieke medewerker

    email_sent = Column(Boolean, default=False)
