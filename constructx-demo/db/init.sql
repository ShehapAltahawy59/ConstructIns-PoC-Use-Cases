-- ConstructX AI demo schema
-- Two modules share this database:
--   1. AI-Assisted Subcontractor Management & Performance Monitoring
--   2. AI-Powered Material Management & Supplier Tracking
-- The API layer (SQLAlchemy) also creates these tables if missing, so this
-- file mainly documents the schema and runs on first container init.

-- ---------------------------------------------------------------------------
-- Module 1: Subcontractor Management
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subcontractors (
    vendor_id         TEXT PRIMARY KEY,
    vendor_name       TEXT NOT NULL,
    trade             TEXT,
    project           TEXT,
    contract_value    NUMERIC(14, 2),
    planned_progress  NUMERIC(6, 2),   -- Planned Progress %
    actual_progress   NUMERIC(6, 2),   -- Actual Progress %
    quality_score     NUMERIC(6, 2),   -- 0-100
    safety_score      NUMERIC(6, 2),   -- 0-100
    inspection_pass   NUMERIC(6, 2),   -- Inspection Pass %
    delay_days        INTEGER,
    open_issues       INTEGER,
    invoice_amount    NUMERIC(14, 2),
    paid_amount       NUMERIC(14, 2),
    engineer_rating   NUMERIC(4, 2),   -- 0-5
    client_rating     NUMERIC(4, 2),   -- 0-5
    active_projects   INTEGER,         -- concurrent projects currently assigned
    capacity_projects INTEGER          -- max concurrent projects the vendor can handle
);

-- Weekly progress reports per subcontractor (live-tracking time series).
CREATE TABLE IF NOT EXISTS progress_updates (
    id            SERIAL PRIMARY KEY,
    vendor_id     TEXT,
    week_date     DATE,
    progress_pct  NUMERIC(6, 2),
    delay_days    INTEGER,
    open_issues   INTEGER,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_progress_vendor ON progress_updates (vendor_id);

-- ---------------------------------------------------------------------------
-- Module 2: Material Management & Supplier Tracking
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materials (
    material_id           TEXT PRIMARY KEY,
    material_name         TEXT NOT NULL,
    category              TEXT,
    current_stock         NUMERIC(14, 2),
    minimum_stock         NUMERIC(14, 2),
    required_qty          NUMERIC(14, 2),
    supplier              TEXT,
    lead_time_days        INTEGER,
    unit_price            NUMERIC(14, 2),
    delivery_reliability  NUMERIC(6, 2),   -- %
    project               TEXT,
    expected_delivery     DATE
);
