from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Enum, Boolean, Text
from sqlalchemy.orm import relationship
import enum
from app.models.base import Base, TimestampMixin


class VehicleStatus(str, enum.Enum):
    INGEKOCHT = "ingekocht"           # Ingekocht, nog niet klaar
    IN_VOORBEREIDING = "in_voorbereiding"  # In de werkplaats voor prep
    KLAAR_VOOR_VERKOOP = "klaar_voor_verkoop"
    VERKOCHT = "verkocht"
    INRUIL = "inruil"
    TAXATIE = "taxatie"


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)

    # Externe systeem-IDs
    vwe_id = Column(String(64), nullable=True, index=True)
    gaston_id = Column(String(64), nullable=True, index=True)
    sam_id = Column(String(64), nullable=True, index=True)

    # Voertuigdata
    license_plate = Column(String(16), nullable=True, index=True)
    vin = Column(String(17), nullable=True, index=True)
    make = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    variant = Column(String(128), nullable=True)
    year = Column(Integer, nullable=True)
    color = Column(String(64), nullable=True)
    mileage = Column(Integer, nullable=True)
    fuel_type = Column(String(32), nullable=True)
    transmission = Column(String(32), nullable=True)

    # APK
    apk_expiry = Column(Date, nullable=True)

    # Financieel
    purchase_price = Column(Float, nullable=True)
    trade_in_value = Column(Float, nullable=True)
    asking_price = Column(Float, nullable=True)
    sale_price = Column(Float, nullable=True)

    status = Column(Enum(VehicleStatus), default=VehicleStatus.INGEKOCHT, nullable=False)

    # Relaties
    owner_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    owner = relationship("Customer", foreign_keys=[owner_id])

    notes = Column(Text, nullable=True)
    is_trade_in = Column(Boolean, default=False)
