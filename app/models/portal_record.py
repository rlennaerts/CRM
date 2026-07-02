from sqlalchemy import Column, Integer, String, JSON, UniqueConstraint
from app.models.base import Base, TimestampMixin


class PortalRecord(Base, TimestampMixin):
    """Generieke opslag voor de Sales Portal.

    De portal praat via één `StorageAdapter`-interface met de backend
    (collecties zoals cars/customers/deals/events). Deze tabel spiegelt dat:
    elk record is één entiteit, opgeslagen als JSON onder (collection, key).
    Zo hoeft de portal-datalaag niet op de integratie-modellen van de hub te
    worden geforceerd, terwijl alles wél server-side persistent is.
    """

    __tablename__ = "portal_records"

    id = Column(Integer, primary_key=True, index=True)
    collection = Column(String(64), nullable=False, index=True)
    key = Column(String(128), nullable=False, index=True)
    data = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("collection", "key", name="uq_portal_collection_key"),
    )
