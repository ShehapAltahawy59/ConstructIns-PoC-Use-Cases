"""SQLAlchemy ORM models mirroring db/init.sql."""
from sqlalchemy import Column, Date, Integer, Numeric, Text

from .database import Base


class Subcontractor(Base):
    __tablename__ = "subcontractors"

    vendor_id = Column(Text, primary_key=True)
    vendor_name = Column(Text, nullable=False)
    trade = Column(Text)
    project = Column(Text)
    contract_value = Column(Numeric(14, 2))
    planned_progress = Column(Numeric(6, 2))
    actual_progress = Column(Numeric(6, 2))
    quality_score = Column(Numeric(6, 2))
    safety_score = Column(Numeric(6, 2))
    inspection_pass = Column(Numeric(6, 2))
    delay_days = Column(Integer)
    open_issues = Column(Integer)
    invoice_amount = Column(Numeric(14, 2))
    paid_amount = Column(Numeric(14, 2))
    engineer_rating = Column(Numeric(4, 2))
    client_rating = Column(Numeric(4, 2))
    active_projects = Column(Integer)
    capacity_projects = Column(Integer)


class ProgressUpdate(Base):
    """A weekly progress report for a subcontractor — the live-tracking time series."""
    __tablename__ = "progress_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Text, index=True)   # references subcontractors.vendor_id
    week_date = Column(Date)
    progress_pct = Column(Numeric(6, 2))
    delay_days = Column(Integer)
    open_issues = Column(Integer)
    note = Column(Text)


class Material(Base):
    __tablename__ = "materials"

    material_id = Column(Text, primary_key=True)
    material_name = Column(Text, nullable=False)
    category = Column(Text)
    current_stock = Column(Numeric(14, 2))
    minimum_stock = Column(Numeric(14, 2))
    required_qty = Column(Numeric(14, 2))
    supplier = Column(Text)
    lead_time_days = Column(Integer)
    unit_price = Column(Numeric(14, 2))
    delivery_reliability = Column(Numeric(6, 2))
    project = Column(Text)
    expected_delivery = Column(Date)
