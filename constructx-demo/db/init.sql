-- ConstructX AI demo schema
-- Model 1: Project -> Assignment -> Subcontractor (company), with progress log.
-- Model 2: Material Management & Supplier Tracking.
-- The API layer (SQLAlchemy) also create_all()s these, so this mainly documents
-- the schema and runs on first container init.

CREATE TABLE IF NOT EXISTS projects (
    project_id        TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    client            TEXT,
    start_date        DATE,
    planned_end_date  DATE,
    status            TEXT
);

CREATE TABLE IF NOT EXISTS subcontractors (
    vendor_id          TEXT PRIMARY KEY,
    company_name       TEXT NOT NULL,
    trade              TEXT,
    capacity_projects  INTEGER
);

CREATE TABLE IF NOT EXISTS subcontracts (
    subcontract_id    TEXT PRIMARY KEY,
    vendor_id         TEXT,
    project_id        TEXT,
    title             TEXT,
    start_date        DATE,
    planned_end_date  DATE,
    status            TEXT,
    retainage_pct     NUMERIC(5, 2),
    retainage_released NUMERIC(14, 2),
    quality_score     NUMERIC(6, 2),
    safety_score      NUMERIC(6, 2),
    inspection_pass   NUMERIC(6, 2),
    delay_days        INTEGER,
    open_issues       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sc_vendor ON subcontracts (vendor_id);
CREATE INDEX IF NOT EXISTS idx_sc_project ON subcontracts (project_id);

CREATE TABLE IF NOT EXISTS sov_lines (
    line_id          TEXT PRIMARY KEY,
    subcontract_id   TEXT,
    cost_code        TEXT,
    description      TEXT,
    scheduled_value  NUMERIC(14, 2),
    percent_complete NUMERIC(6, 2)
);
CREATE INDEX IF NOT EXISTS idx_sov_sc ON sov_lines (subcontract_id);

CREATE TABLE IF NOT EXISTS progress_claims (
    claim_id         TEXT PRIMARY KEY,
    subcontract_id   TEXT,
    period_end       DATE,
    percent_complete NUMERIC(6, 2),
    completed_value  NUMERIC(14, 2),
    note             TEXT
);
CREATE INDEX IF NOT EXISTS idx_claim_sc ON progress_claims (subcontract_id);

CREATE TABLE IF NOT EXISTS change_orders (
    co_id           TEXT PRIMARY KEY,
    subcontract_id  TEXT,
    description     TEXT,
    amount          NUMERIC(14, 2),
    status          TEXT,
    co_date         DATE
);
CREATE INDEX IF NOT EXISTS idx_co_sc ON change_orders (subcontract_id);

-- Module 2: material procurement (Project → PO → Delivery)
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    material_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT,
    unit         TEXT
);

CREATE TABLE IF NOT EXISTS material_requirements (
    req_id        TEXT PRIMARY KEY,
    project_id    TEXT,
    material_id   TEXT,
    required_qty  NUMERIC(14, 2),
    minimum_stock NUMERIC(14, 2),
    consumed_qty  NUMERIC(14, 2)
);
CREATE INDEX IF NOT EXISTS idx_req_project ON material_requirements (project_id);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id             TEXT PRIMARY KEY,
    supplier_id       TEXT,
    project_id        TEXT,
    order_date        DATE,
    expected_delivery DATE,
    status            TEXT
);

CREATE TABLE IF NOT EXISTS po_lines (
    line_id      TEXT PRIMARY KEY,
    po_id        TEXT,
    material_id  TEXT,
    qty_ordered  NUMERIC(14, 2),
    unit_price   NUMERIC(14, 2)
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id   TEXT PRIMARY KEY,
    po_id         TEXT,
    material_id   TEXT,
    project_id    TEXT,
    qty_received  NUMERIC(14, 2),
    qty_rejected  NUMERIC(14, 2),
    order_date    DATE,
    expected_date DATE,
    received_date DATE
);
CREATE INDEX IF NOT EXISTS idx_del_pm ON deliveries (project_id, material_id);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id   TEXT PRIMARY KEY,
    po_id        TEXT,
    supplier_id  TEXT,
    invoice_date DATE,
    billed_qty   NUMERIC(14, 2),
    amount       NUMERIC(14, 2),
    status       TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_po ON invoices (po_id);
