"""Subcontracts API — the commitment (plan), its Schedule of Values, Earned-Value
metrics, and monthly progress claims (the S-curve)."""
import datetime as dt

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cache, scoring
from ..ai import evm
from ..ai import subcontractor as ai
from ..database import get_db
from ..models import (
    ChangeOrder, ProgressClaim, Project, SovLine, Subcontract, Subcontractor,
)


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

router = APIRouter(prefix="/api/subcontracts", tags=["Subcontracts"])


def _sov(db, sid):
    return db.query(SovLine).filter(SovLine.subcontract_id == sid).all()


def _enrich(s, db):
    lines = _sov(db, s.subcontract_id)
    m = evm.metrics(s, lines)
    s.contract_value = m["contract_value"]
    s.planned_progress = m["planned_progress"]
    s.actual_progress = m["actual_progress"]
    s.invoice_amount = m["billed_to_date"]
    s.paid_amount = m["net_paid"]
    c = db.get(Subcontractor, s.vendor_id)
    p = db.get(Project, s.project_id)
    s.company_name = c.company_name if c else ""
    s.trade = c.trade if c else ""
    s.project_name = p.name if p else s.project_id
    n = db.query(Subcontract).filter(Subcontract.vendor_id == s.vendor_id).count()
    cap = int(c.capacity_projects) if c and c.capacity_projects else 0
    s.utilization = round(n / cap * 100) if cap else 0
    return s, m, lines


@router.get("/{sid}")
def detail(sid: str, db: Session = Depends(get_db)):
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    s, m, lines = _enrich(s, db)
    ev = ai.evaluate_all_assignments([s])[0]
    claims = (db.query(ProgressClaim)
              .filter(ProgressClaim.subcontract_id == sid)
              .order_by(ProgressClaim.period_end).all())
    cos = (db.query(ChangeOrder).filter(ChangeOrder.subcontract_id == sid)
           .order_by(ChangeOrder.co_date).all())
    co_total = sum(_f(c.amount) for c in cos if c.status == "Approved")
    return {
        "subcontract_id": sid, "title": s.title,
        "company": s.company_name, "trade": s.trade, "project": s.project_name,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "planned_end_date": s.planned_end_date.isoformat() if s.planned_end_date else None,
        "status": s.status, "evm": m, "evaluation": ev,
        "original_value": round(m["contract_value"] - co_total, 2),
        "approved_co_total": round(co_total, 2),
        "sov": [{"line_id": l.line_id, "cost_code": l.cost_code,
                 "description": l.description,
                 "scheduled_value": float(l.scheduled_value or 0),
                 "percent_complete": float(l.percent_complete or 0)} for l in lines],
        "claims": [{"period_end": c.period_end.isoformat() if c.period_end else None,
                    "percent_complete": float(c.percent_complete or 0),
                    "completed_value": float(c.completed_value or 0)} for c in claims],
        "change_orders": [{"co_id": c.co_id, "description": c.description,
                           "amount": float(c.amount or 0), "status": c.status,
                           "co_date": c.co_date.isoformat() if c.co_date else None}
                          for c in cos],
    }


@router.post("")
def create(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Create a subcontract = the plan (company, project, dates, retainage, SOV)."""
    sid = (payload.get("subcontract_id") or "").strip()
    vid = (payload.get("vendor_id") or "").strip()
    pid = (payload.get("project_id") or "").strip()
    if not (sid and vid and pid):
        raise HTTPException(status_code=400,
                            detail="subcontract_id, vendor_id, project_id required")

    if db.get(Subcontractor, vid) is None:
        db.add(Subcontractor(
            vendor_id=vid, company_name=payload.get("company_name") or vid,
            trade=payload.get("trade"),
            capacity_projects=int(float(payload["capacity_projects"]))
            if payload.get("capacity_projects") not in (None, "") else 3))
    if db.get(Project, pid) is None:
        db.add(Project(project_id=pid, name=payload.get("project_name") or pid,
                       status="Active"))

    s = db.get(Subcontract, sid) or Subcontract(subcontract_id=sid)
    s.vendor_id, s.project_id = vid, pid
    s.title = payload.get("title") or f"{payload.get('trade', '')} — {pid}"
    s.status = payload.get("status") or "Active"
    for k in ("start_date", "planned_end_date"):
        if payload.get(k):
            setattr(s, k, dt.date.fromisoformat(payload[k]))
    if payload.get("retainage_pct") not in (None, ""):
        s.retainage_pct = float(payload["retainage_pct"])
    if s not in db:
        db.add(s)

    # Replace SOV lines if provided.
    sov = payload.get("sov") or []
    if sov:
        db.query(SovLine).filter(SovLine.subcontract_id == sid).delete(
            synchronize_session=False)
        for i, line in enumerate(sov, start=1):
            if line.get("scheduled_value") in (None, ""):
                continue
            db.add(SovLine(
                line_id=f"{sid}-L{i}", subcontract_id=sid,
                cost_code=line.get("cost_code") or f"L{i}",
                description=line.get("description") or "",
                scheduled_value=float(line["scheduled_value"]),
                percent_complete=float(line.get("percent_complete") or 0)))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "subcontract_id": sid}


@router.post("/{sid}/claim")
def add_claim(sid: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Log a progress claim: update % complete per SOV line for a period."""
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    lines = {l.line_id: l for l in _sov(db, sid)}
    for upd in payload.get("lines", []):
        line = lines.get(upd.get("line_id"))
        if line is not None and upd.get("percent_complete") not in (None, ""):
            line.percent_complete = float(upd["percent_complete"])
    m = evm.metrics(s, list(lines.values()))
    period = payload.get("period_end")
    period_date = dt.date.fromisoformat(period) if period else dt.date.today()
    n = db.query(ProgressClaim).filter(
        ProgressClaim.subcontract_id == sid).count()
    db.add(ProgressClaim(
        claim_id=f"{sid}-C{n + 1}", subcontract_id=sid, period_end=period_date,
        percent_complete=m["actual_progress"], completed_value=m["earned_value"],
        note=payload.get("note")))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "actual_progress": m["actual_progress"]}


@router.post("/{sid}/change-order")
def add_change_order(sid: str, payload: dict = Body(...),
                     db: Session = Depends(get_db)):
    """Raise a change order (Pending until approved)."""
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    n = db.query(ChangeOrder).filter(ChangeOrder.subcontract_id == sid).count()
    period = payload.get("co_date")
    db.add(ChangeOrder(
        co_id=f"{sid}-CO{n + 1}", subcontract_id=sid,
        description=payload.get("description") or "Change order",
        amount=_f(payload.get("amount")),
        status="Pending",
        co_date=dt.date.fromisoformat(period) if period else dt.date.today()))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "co_id": f"{sid}-CO{n + 1}"}


@router.post("/{sid}/change-order/{co_id}/approve")
def approve_change_order(sid: str, co_id: str, db: Session = Depends(get_db)):
    """Approve a change order — adds its value to the contract as a new SOV line."""
    co = db.get(ChangeOrder, co_id)
    if co is None or co.subcontract_id != sid:
        raise HTTPException(status_code=404, detail="Change order not found")
    if co.status != "Approved":
        co.status = "Approved"
        db.add(SovLine(
            line_id=f"{sid}-CO-{co_id}", subcontract_id=sid,
            cost_code=f"CO-{co_id.split('-')[-1]}",
            description=f"Change order: {co.description}",
            scheduled_value=_f(co.amount), percent_complete=0))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True}


@router.delete("/{sid}/change-order/{co_id}")
def delete_change_order(sid: str, co_id: str, db: Session = Depends(get_db)):
    co = db.get(ChangeOrder, co_id)
    if co is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    if co.status == "Approved":
        db.query(SovLine).filter(
            SovLine.line_id == f"{sid}-CO-{co_id}").delete(synchronize_session=False)
    db.delete(co)
    db.commit()
    cache.bump("subcontractors")
    return {"deleted": co_id}


@router.post("/{sid}/release-retainage")
def release_retainage(sid: str, db: Session = Depends(get_db)):
    """Release the retainage held to date (e.g. at substantial completion)."""
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    m = evm.metrics(s, _sov(db, sid))
    s.retainage_released = m["retainage_held"]   # release everything held to date
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "released": m["retainage_held"]}


@router.post("/{sid}/inspection")
def log_inspection(sid: str, payload: dict = Body(...),
                   db: Session = Depends(get_db)):
    """Log inspection & safety records; recompute quality/safety scores."""
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    q = scoring.quality_and_inspection(
        payload.get("inspections_total", 0), payload.get("inspections_passed", 0),
        payload.get("ncrs_raised", 0), payload.get("ncrs_closed", 0))
    sf = scoring.safety(payload.get("recordable_incidents", 0),
                        payload.get("man_hours", 0))
    if q["quality_score"] is not None:
        s.quality_score = q["quality_score"]
        s.inspection_pass = q["inspection_pass"]
    if sf["safety_score"] is not None:
        s.safety_score = sf["safety_score"]
    if payload.get("delay_days") not in (None, ""):
        s.delay_days = int(float(payload["delay_days"]))
    if payload.get("open_issues") not in (None, ""):
        s.open_issues = int(float(payload["open_issues"]))
    db.commit()
    cache.bump("subcontractors")
    return {"ok": True, "quality_score": s.quality_score,
            "safety_score": s.safety_score, "inspection_pass": s.inspection_pass}


@router.delete("/{sid}")
def delete(sid: str, db: Session = Depends(get_db)):
    s = db.get(Subcontract, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Subcontract not found")
    db.query(ProgressClaim).filter(
        ProgressClaim.subcontract_id == sid).delete(synchronize_session=False)
    db.query(SovLine).filter(
        SovLine.subcontract_id == sid).delete(synchronize_session=False)
    db.query(ChangeOrder).filter(
        ChangeOrder.subcontract_id == sid).delete(synchronize_session=False)
    db.delete(s)
    db.commit()
    cache.bump("subcontractors")
    return {"deleted": sid}
