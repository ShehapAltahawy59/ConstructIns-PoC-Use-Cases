"""Module 1 API — companies ranked by AI performance across their subcontracts.

Each subcontract is enriched with Earned-Value metrics (planned % from the
baseline schedule, actual % from the SOV-weighted progress) before scoring, then
rolled up to the company level.
"""
from collections import defaultdict

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import cache, import_workbook
from ..ai import evm, portfolio
from ..ai import subcontractor as ai
from ..database import get_db
from ..ml import registry
from ..models import (
    ProgressClaim, Project, SovLine, Subcontract, Subcontractor,
)

router = APIRouter(prefix="/api/subcontractors", tags=["Subcontractor Management"])


def _companies(db):
    return db.query(Subcontractor).all()


def _enriched(db):
    """Subcontracts enriched with EVM-derived plan/actual/cost + company/project."""
    subs = db.query(Subcontract).all()
    companies = {c.vendor_id: c for c in _companies(db)}
    projects = {p.project_id: p for p in db.query(Project).all()}
    sov_by = defaultdict(list)
    for l in db.query(SovLine).all():
        sov_by[l.subcontract_id].append(l)
    counts = defaultdict(int)
    for s in subs:
        counts[s.vendor_id] += 1

    for s in subs:
        m = evm.metrics(s, sov_by.get(s.subcontract_id, []))
        s.contract_value = m["contract_value"]
        s.planned_progress = m["planned_progress"]
        s.actual_progress = m["actual_progress"]
        s.invoice_amount = m["billed_to_date"]
        s.paid_amount = m["net_paid"]
        s.evm = m
        c = companies.get(s.vendor_id)
        p = projects.get(s.project_id)
        s.company_name = c.company_name if c else ""
        s.trade = c.trade if c else ""
        s.project_name = p.name if p else s.project_id
        cap = int(c.capacity_projects) if c and c.capacity_projects else 0
        s.utilization = round(counts[s.vendor_id] / cap * 100) if cap else 0
    return subs


def _assign_evals(db):
    return cache.cached("sub_eval", "subcontractors",
                        lambda: ai.evaluate_all_assignments(_enriched(db)))


def _rollup(db):
    return cache.cached("sub_rollup", "subcontractors",
                        lambda: ai.aggregate_companies(_assign_evals(db), _companies(db)))


@router.get("/companies")
def companies(db: Session = Depends(get_db)):
    return _rollup(db)


@router.get("/raw")
def raw_companies(db: Session = Depends(get_db)):
    return [{"vendor_id": c.vendor_id, "company_name": c.company_name,
             "trade": c.trade, "capacity_projects": c.capacity_projects}
            for c in _companies(db)]


@router.get("/{vendor_id}/subcontracts")
def company_subcontracts(vendor_id: str, db: Session = Depends(get_db)):
    comp = db.get(Subcontractor, vendor_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Company not found")
    items = [e for e in _assign_evals(db) if e["vendor_id"] == vendor_id]
    return {"vendor_id": vendor_id, "company": comp.company_name,
            "trade": comp.trade, "capacity_projects": comp.capacity_projects,
            "subcontracts": items}


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    rollup = [r for r in _rollup(db) if r["evaluable"]]
    return {
        "delay_alerts": [{"vendor": r["company"], "delay_risk": r["delay_risk"]}
                         for r in rollup if r["delay_risk"] in ("Medium", "High")],
        "breach_alerts": [{"vendor": r["company"],
                           "contract_breach_risk": r["contract_breach_risk"]}
                          for r in rollup
                          if r["contract_breach_risk"] in ("Medium", "High")],
    }


@router.get("/concentration")
def concentration(db: Session = Depends(get_db)):
    subs = _enriched(db)
    comp_by = {c.vendor_id: c for c in _companies(db)}
    return {"summary": portfolio.concentration_summary(subs, comp_by),
            "by_trade": portfolio.concentration_by_trade(subs, comp_by)}


@router.get("/capacity")
def capacity(db: Session = Depends(get_db)):
    rollup = _rollup(db)
    return {"summary": portfolio.capacity_summary(rollup),
            "vendors": portfolio.capacity_list(rollup)}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    rollup = _rollup(db)
    total = len(rollup)
    if not total:
        return {"total_vendors": 0, "rated_vendors": 0, "new_vendors": 0,
                "total_assignments": 0, "avg_ai_score": None, "high_delay_risk": 0,
                "high_breach_risk": 0, "preferred_vendors": 0, "top_vendor": None,
                "high_concentration_trades": 0, "overloaded_vendors": 0}
    rated = [r for r in rollup if r["evaluable"]]
    subs = _enriched(db)
    comp_by = {c.vendor_id: c for c in _companies(db)}
    conc = portfolio.concentration_summary(subs, comp_by)
    cap = portfolio.capacity_summary(rollup)
    return {
        "total_vendors": total,
        "rated_vendors": len(rated),
        "new_vendors": total - len(rated),
        "total_assignments": len(subs),
        "avg_ai_score": round(sum(r["avg_score"] for r in rated) / len(rated), 1)
        if rated else None,
        "high_delay_risk": sum(1 for r in rated if r["delay_risk"] == "High"),
        "high_breach_risk": sum(1 for r in rated
                                if r["contract_breach_risk"] == "High"),
        "preferred_vendors": sum(1 for r in rated
                                 if r["recommendation"] == "Preferred Vendor"),
        "top_vendor": rated[0]["company"] if rated else None,
        "high_concentration_trades": conc["high_concentration_trades"],
        "overloaded_vendors": cap["overloaded_vendors"],
    }


@router.get("/model-info")
def model_info():
    return registry.model_info(
        ["sub_score", "sub_delay", "sub_breach", "sub_reco"])


@router.post("/import")
async def import_workbook_data(file: UploadFile = File(...),
                              db: Session = Depends(get_db)):
    """Import a filled Subcontractor workbook (.xlsx) — replaces module data."""
    content = await file.read()
    try:
        counts = import_workbook.import_subcontractor(content, db)
    except Exception as exc:                                  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}")
    cache.bump("subcontractors")
    return {"ok": True, "imported": counts}


@router.post("")
def add_company(payload: dict = Body(...), db: Session = Depends(get_db)):
    vid = (payload.get("vendor_id") or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="Company ID is required")
    obj = db.get(Subcontractor, vid)
    if obj is None:
        if not payload.get("company_name"):
            raise HTTPException(status_code=400,
                                detail="Company Name is required for a new company")
        obj = Subcontractor(vendor_id=vid)
        db.add(obj)
    for k in ("company_name", "trade"):
        if payload.get(k) is not None:
            setattr(obj, k, payload[k])
    if payload.get("capacity_projects") not in (None, ""):
        obj.capacity_projects = int(float(payload["capacity_projects"]))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "vendor_id": vid}


@router.delete("/{vendor_id}")
def delete_company(vendor_id: str, db: Session = Depends(get_db)):
    obj = db.get(Subcontractor, vendor_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Company not found")
    sc_ids = [s.subcontract_id for s in db.query(Subcontract)
              .filter(Subcontract.vendor_id == vendor_id).all()]
    if sc_ids:
        db.query(ProgressClaim).filter(
            ProgressClaim.subcontract_id.in_(sc_ids)).delete(synchronize_session=False)
        db.query(SovLine).filter(
            SovLine.subcontract_id.in_(sc_ids)).delete(synchronize_session=False)
        db.query(Subcontract).filter(
            Subcontract.vendor_id == vendor_id).delete(synchronize_session=False)
    db.delete(obj)
    db.commit()
    cache.bump("subcontractors")
    return {"deleted": vendor_id}
