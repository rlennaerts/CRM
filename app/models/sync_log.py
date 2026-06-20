from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, JSON
from app.models.base import Base, TimestampMixin
import enum


class SyncSource(str, enum.Enum):
    VWE = "vwe"
    GASTON = "gaston"
    SAM = "sam"


class SyncStatus(str, enum.Enum):
    GESTART = "gestart"
    SUCCES = "succes"
    GEDEELTELIJK = "gedeeltelijk"
    FOUT = "fout"


class SyncLog(Base, TimestampMixin):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(Enum(SyncSource), nullable=False, index=True)
    status = Column(Enum(SyncStatus), nullable=False)

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)

    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
