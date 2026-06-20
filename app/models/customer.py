from sqlalchemy import Column, Integer, String, Boolean, Text
from app.models.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    # Externe systeem-IDs
    vwe_id = Column(String(64), unique=True, nullable=True, index=True)
    gaston_id = Column(String(64), unique=True, nullable=True, index=True)
    sam_id = Column(String(64), unique=True, nullable=True, index=True)

    # NAW
    first_name = Column(String(128))
    last_name = Column(String(128))
    company_name = Column(String(256), nullable=True)
    email = Column(String(256), nullable=True, index=True)
    phone = Column(String(32), nullable=True)
    mobile = Column(String(32), nullable=True)
    street = Column(String(256), nullable=True)
    house_number = Column(String(16), nullable=True)
    postal_code = Column(String(16), nullable=True)
    city = Column(String(128), nullable=True)

    is_business = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
