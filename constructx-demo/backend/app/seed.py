"""Seed the database on first startup.

Module 1: projects, companies, subcontracts, SOV, progress claims.
Module 2: suppliers, materials, requirements (BOQ), purchase orders, deliveries.
"""
import os

from . import seed_data
from .database import SessionLocal
from .models import (
    Delivery, Invoice, Material, MaterialRequirement, POLine, ProgressClaim,
    Project, PurchaseOrder, SovLine, Subcontract, Subcontractor, Supplier,
)


def seed_subcontractor_model(db) -> None:
    projects, companies, subs, sov, claims = seed_data.generate()
    for p in projects:
        db.add(Project(**p))
    for c in companies:
        db.add(Subcontractor(**c))
    for s in subs:
        db.add(Subcontract(**s))
    for l in sov:
        db.add(SovLine(**l))
    for cl in claims:
        db.add(ProgressClaim(**cl))
    db.commit()
    print(f"[seed] {len(projects)} projects, {len(companies)} companies, "
          f"{len(subs)} subcontracts, {len(sov)} SOV lines, {len(claims)} claims")


def seed_procurement(db) -> None:
    suppliers, materials, reqs, pos, lines, deliveries, invoices = \
        seed_data.generate_procurement()
    for s in suppliers:
        db.add(Supplier(**s))
    for m in materials:
        db.add(Material(**m))
    for r in reqs:
        db.add(MaterialRequirement(**r))
    for p in pos:
        db.add(PurchaseOrder(**p))
    for l in lines:
        db.add(POLine(**l))
    for d in deliveries:
        db.add(Delivery(**d))
    for iv in invoices:
        db.add(Invoice(**iv))
    db.commit()
    print(f"[seed] {len(suppliers)} suppliers, {len(materials)} materials, "
          f"{len(reqs)} requirements, {len(pos)} POs, {len(deliveries)} deliveries, "
          f"{len(invoices)} invoices")


def run_seed() -> None:
    """The system starts EMPTY — companies import their own workbooks.
    Set SEED_DEMO_DATA=true to load the sample dataset instead."""
    if os.getenv("SEED_DEMO_DATA", "false").lower() not in ("1", "true", "yes"):
        print("[seed] starting empty (import a workbook to load data)")
        return
    db = SessionLocal()
    try:
        if db.query(Subcontractor).count() == 0:
            seed_subcontractor_model(db)
        if db.query(Supplier).count() == 0:
            seed_procurement(db)
    finally:
        db.close()
