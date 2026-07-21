"""SQLAlchemy ORM models — Procore-style commitment / SOV model.

    Project ──< Subcontract (commitment) >── Subcontractor (company)
                    │
                    ├──< SovLine        (Schedule of Values: cost-code line items)
                    └──< ProgressClaim  (monthly progress billing → the S-curve)

The PLAN is the subcontract + its Schedule of Values (scheduled value per line)
and baseline dates. Planned % is read from the baseline schedule at today's date;
actual % is the SOV-weighted % complete from the latest progress claim. Quality /
safety / delay accrue during execution (null until inspections/incidents logged).
"""
from sqlalchemy import Column, Date, Integer, Numeric, Text

from .database import Base


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    client = Column(Text)
    start_date = Column(Date)
    planned_end_date = Column(Date)
    status = Column(Text)


class Subcontractor(Base):
    __tablename__ = "subcontractors"

    vendor_id = Column(Text, primary_key=True)
    company_name = Column(Text, nullable=False)
    trade = Column(Text)
    capacity_projects = Column(Integer)


class Subcontract(Base):
    """A subcontractor's commitment on a project — the plan + accruing performance."""
    __tablename__ = "subcontracts"

    subcontract_id = Column(Text, primary_key=True)
    vendor_id = Column(Text, index=True)
    project_id = Column(Text, index=True)
    title = Column(Text)
    start_date = Column(Date)            # baseline schedule start
    planned_end_date = Column(Date)      # baseline schedule finish
    status = Column(Text)                # Active / Complete
    retainage_pct = Column(Numeric(5, 2))
    retainage_released = Column(Numeric(14, 2))   # amount of retainage released
    # Performance snapshots (accrue from inspections/incidents; null until logged):
    quality_score = Column(Numeric(6, 2))
    safety_score = Column(Numeric(6, 2))
    inspection_pass = Column(Numeric(6, 2))
    delay_days = Column(Integer)
    open_issues = Column(Integer)


class SovLine(Base):
    """A Schedule-of-Values line item (cost code + scheduled value + % complete)."""
    __tablename__ = "sov_lines"

    line_id = Column(Text, primary_key=True)
    subcontract_id = Column(Text, index=True)
    cost_code = Column(Text)
    description = Column(Text)
    scheduled_value = Column(Numeric(14, 2))
    percent_complete = Column(Numeric(6, 2))   # current cumulative %


class ProgressClaim(Base):
    """A monthly progress billing — the actual %/value completed to that date."""
    __tablename__ = "progress_claims"

    claim_id = Column(Text, primary_key=True)
    subcontract_id = Column(Text, index=True)
    period_end = Column(Date)
    percent_complete = Column(Numeric(6, 2))     # SOV-weighted % to date
    completed_value = Column(Numeric(14, 2))     # earned value to date
    note = Column(Text)


class ChangeOrder(Base):
    """A change to a subcontract's scope/value. Approved COs add an SOV line."""
    __tablename__ = "change_orders"

    co_id = Column(Text, primary_key=True)
    subcontract_id = Column(Text, index=True)
    description = Column(Text)
    amount = Column(Numeric(14, 2))       # +/- change to contract value
    status = Column(Text)                 # Pending / Approved
    co_date = Column(Date)


# ---------------------------------------------------------------------------
# Module 2: Material procurement (Project → Purchase Order → Delivery model)
#   Supplier, Material (catalog), MaterialRequirement (BOQ per project),
#   PurchaseOrder (commitment) + POLine, Delivery (GRN = actual receipt).
#   Stock, lead time and reliability are DERIVED from deliveries, never typed.
# ---------------------------------------------------------------------------
class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    category = Column(Text)


class Material(Base):
    """Item master (catalog)."""
    __tablename__ = "materials"

    material_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    category = Column(Text)
    unit = Column(Text)


class MaterialRequirement(Base):
    """A project's requirement for a material (BOQ line + reorder point)."""
    __tablename__ = "material_requirements"

    req_id = Column(Text, primary_key=True)
    project_id = Column(Text, index=True)
    material_id = Column(Text, index=True)
    required_qty = Column(Numeric(14, 2))
    minimum_stock = Column(Numeric(14, 2))
    consumed_qty = Column(Numeric(14, 2))    # used on site (depletes stock)


class PurchaseOrder(Base):
    """A commitment to a supplier for materials on a project."""
    __tablename__ = "purchase_orders"

    po_id = Column(Text, primary_key=True)
    supplier_id = Column(Text, index=True)
    project_id = Column(Text, index=True)
    order_date = Column(Date)
    expected_delivery = Column(Date)
    status = Column(Text)                    # Open / Received / Closed


class POLine(Base):
    __tablename__ = "po_lines"

    line_id = Column(Text, primary_key=True)
    po_id = Column(Text, index=True)
    material_id = Column(Text)
    qty_ordered = Column(Numeric(14, 2))
    unit_price = Column(Numeric(14, 2))


class Delivery(Base):
    """Goods Receipt Note — an actual delivery against a PO."""
    __tablename__ = "deliveries"

    delivery_id = Column(Text, primary_key=True)
    po_id = Column(Text, index=True)
    material_id = Column(Text, index=True)
    project_id = Column(Text, index=True)
    qty_received = Column(Numeric(14, 2))
    qty_rejected = Column(Numeric(14, 2))    # defective goods rejected on receipt
    order_date = Column(Date)
    expected_date = Column(Date)
    received_date = Column(Date)


class Invoice(Base):
    """A supplier invoice against a PO — the 3rd leg of the 3-way match."""
    __tablename__ = "invoices"

    invoice_id = Column(Text, primary_key=True)
    po_id = Column(Text, index=True)
    supplier_id = Column(Text)
    invoice_date = Column(Date)
    billed_qty = Column(Numeric(14, 2))
    amount = Column(Numeric(14, 2))
    status = Column(Text)                    # Pending / Matched / Exception
