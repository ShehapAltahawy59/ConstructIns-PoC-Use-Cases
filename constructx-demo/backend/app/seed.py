"""Load the CSV datasets into PostgreSQL on first startup."""
import csv
import datetime as dt
import os

from .database import SessionLocal
from .models import Material, Subcontractor

DATA_DIR = os.getenv("DATA_DIR", "/code/data")


def _int(v):
    v = (v or "").strip()
    return int(float(v)) if v else None


def _num(v):
    v = (v or "").strip()
    return float(v) if v else None


def _date(v):
    v = (v or "").strip()
    if not v:
        return None
    return dt.date.fromisoformat(v)


def seed_subcontractors(db) -> int:
    path = os.path.join(DATA_DIR, "subcontractors.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        count = 0
        for r in reader:
            if not r or not r[0].strip():
                continue
            db.add(Subcontractor(
                vendor_id=r[0].strip(),
                vendor_name=r[1].strip(),
                trade=r[2].strip(),
                project=r[3].strip(),
                contract_value=_num(r[4]),
                planned_progress=_num(r[5]),
                actual_progress=_num(r[6]),
                quality_score=_num(r[7]),
                safety_score=_num(r[8]),
                inspection_pass=_num(r[9]),
                delay_days=_int(r[10]),
                open_issues=_int(r[11]),
                invoice_amount=_num(r[12]),
                paid_amount=_num(r[13]),
                engineer_rating=_num(r[14]),
                client_rating=_num(r[15]),
                active_projects=_int(r[16]),
                capacity_projects=_int(r[17]),
            ))
            count += 1
        db.commit()
        return count


def seed_materials(db) -> int:
    path = os.path.join(DATA_DIR, "materials.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        count = 0
        for r in reader:
            if not r or not r[0].strip():
                continue
            db.add(Material(
                material_id=r[0].strip(),
                material_name=r[1].strip(),
                category=r[2].strip(),
                current_stock=_num(r[3]),
                minimum_stock=_num(r[4]),
                required_qty=_num(r[5]),
                supplier=r[6].strip(),
                lead_time_days=_int(r[7]),
                unit_price=_num(r[8]),
                delivery_reliability=_num(r[9]),
                project=r[10].strip(),
                expected_delivery=_date(r[11]),
            ))
            count += 1
        db.commit()
        return count


def run_seed() -> None:
    """Seed both tables if they are empty (idempotent)."""
    db = SessionLocal()
    try:
        if db.query(Subcontractor).count() == 0:
            n = seed_subcontractors(db)
            print(f"[seed] inserted {n} subcontractors")
        if db.query(Material).count() == 0:
            n = seed_materials(db)
            print(f"[seed] inserted {n} materials")
    finally:
        db.close()
