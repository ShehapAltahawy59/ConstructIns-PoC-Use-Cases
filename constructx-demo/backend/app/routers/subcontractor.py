"""Module 1 API: AI-Assisted Subcontractor Management & Performance Monitoring."""
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import datetime as dt

from .. import ingest
from ..ai import portfolio
from ..ai import subcontractor as ai
from ..ai import tracking
from ..database import get_db
from ..ml import registry
from ..models import ProgressUpdate, Subcontractor

router = APIRouter(prefix="/api/subcontractors", tags=["Subcontractor Management"])


def _all(db: Session):
    return db.query(Subcontractor).all()


@router.get("/raw")
def raw_data(db: Session = Depends(get_db)):
    """Raw subcontractor input data (as ingested from company systems)."""
    rows = _all(db)
    return [
        {
            "vendor_id": r.vendor_id,
            "vendor_name": r.vendor_name,
            "trade": r.trade,
            "project": r.project,
            "contract_value": float(r.contract_value or 0),
            "planned_progress": float(r.planned_progress or 0),
            "actual_progress": float(r.actual_progress or 0),
            "quality_score": float(r.quality_score or 0),
            "safety_score": float(r.safety_score or 0),
            "inspection_pass": float(r.inspection_pass or 0),
            "delay_days": r.delay_days,
            "open_issues": r.open_issues,
            "invoice_amount": float(r.invoice_amount or 0),
            "paid_amount": float(r.paid_amount or 0),
            "engineer_rating": float(r.engineer_rating or 0),
            "client_rating": float(r.client_rating or 0),
            "active_projects": r.active_projects,
            "capacity_projects": r.capacity_projects,
        }
        for r in rows
    ]


@router.get("/evaluate")
def evaluate(db: Session = Depends(get_db)):
    """AI evaluation + ranking for every subcontractor (main dashboard feed)."""
    return ai.evaluate_all(_all(db))


@router.get("/rankings")
def rankings(db: Session = Depends(get_db)):
    """Vendor rankings (vendor, score, risks, recommendation)."""
    results = ai.evaluate_all(_all(db))
    return [
        {
            "rank": r["rank"],
            "vendor": r["vendor"],
            "ai_score": r["ai_score"],
            "delay_risk": r["delay_risk"],
            "contract_breach_risk": r["contract_breach_risk"],
            "recommendation": r["recommendation"],
        }
        for r in results
    ]


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    """Delay-risk and contract-breach alerts for at-risk vendors."""
    results = ai.evaluate_all(_all(db))
    return {
        "delay_alerts": [
            {"vendor": r["vendor"], "project": r["project"],
             "delay_risk": r["delay_risk"]}
            for r in results if r["delay_risk"] in ("Medium", "High")
        ],
        "breach_alerts": [
            {"vendor": r["vendor"], "project": r["project"],
             "contract_breach_risk": r["contract_breach_risk"]}
            for r in results if r["contract_breach_risk"] in ("Medium", "High")
        ],
    }


@router.get("/recommended")
def recommended(db: Session = Depends(get_db)):
    """Vendors recommended as preferred for future projects."""
    results = ai.evaluate_all(_all(db))
    return [r for r in results if r["recommendation"] == "Preferred Vendor"]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Executive-dashboard KPI summary."""
    results = ai.evaluate_all(_all(db))
    total = len(results)
    if not total:
        return {"total_vendors": 0}
    high_delay = sum(1 for r in results if r["delay_risk"] == "High")
    high_breach = sum(1 for r in results
                      if r["contract_breach_risk"] == "High")
    preferred = sum(1 for r in results
                    if r["recommendation"] == "Preferred Vendor")
    avg_score = round(sum(r["ai_score"] for r in results) / total, 1)
    rows = _all(db)
    conc = portfolio.concentration_summary(rows)
    cap = portfolio.capacity_summary(rows)
    return {
        "total_vendors": total,
        "avg_ai_score": avg_score,
        "high_delay_risk": high_delay,
        "high_breach_risk": high_breach,
        "preferred_vendors": preferred,
        "top_vendor": results[0]["vendor"],
        "top_score": results[0]["ai_score"],
        "high_concentration_trades": conc["high_concentration_trades"],
        "overloaded_vendors": cap["overloaded_vendors"],
    }


@router.get("/concentration")
def concentration(db: Session = Depends(get_db)):
    """Vendor-concentration / monopoly risk per trade (HHI index)."""
    rows = _all(db)
    return {
        "summary": portfolio.concentration_summary(rows),
        "by_trade": portfolio.concentration_by_trade(rows),
    }


@router.get("/capacity")
def capacity(db: Session = Depends(get_db)):
    """Workforce capacity / overload analysis per vendor."""
    rows = _all(db)
    return {
        "summary": portfolio.capacity_summary(rows),
        "vendors": portfolio.capacity_analysis(rows),
    }


@router.post("/upload")
async def upload_data(
    file: UploadFile = File(...),
    mode: str = Query("append", pattern="^(append|replace)$"),
    db: Session = Depends(get_db),
):
    """Upload live data (CSV/Excel). mode=append updates by ID; replace clears first."""
    content = await file.read()
    try:
        rows = ingest.parse_table(content, file.filename)
        records, warnings = ingest.rows_to_records(rows, ingest.SUB_SPEC)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not records:
        raise HTTPException(status_code=400,
                            detail="; ".join(warnings) or "No valid rows found")
    result = ingest.upsert(db, Subcontractor, ingest.SUB_SPEC, records,
                           replace=(mode == "replace"))
    result["warnings"] = warnings[:20]
    return result


@router.post("")
def add_vendor(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Add or update a subcontractor. New records need a name; existing ones can
    be patched with any subset of fields (for live incremental updates)."""
    rec = ingest.coerce_record(payload, ingest.SUB_SPEC)
    if not rec.get("vendor_id"):
        raise HTTPException(status_code=400, detail="Vendor ID is required")
    exists = db.get(Subcontractor, rec["vendor_id"]) is not None
    if not exists and not rec.get("vendor_name"):
        raise HTTPException(status_code=400,
                            detail="Vendor Name is required for a new vendor")
    return {"ok": True,
            **ingest.upsert(db, Subcontractor, ingest.SUB_SPEC, [rec])}


@router.get("/template.csv")
def template():
    """Download a blank CSV template with the correct columns."""
    return PlainTextResponse(
        ingest.template_csv(ingest.SUB_SPEC),
        headers={"Content-Disposition":
                 "attachment; filename=subcontractors_template.csv"},
    )


@router.get("/model-info")
def model_info():
    """Trained-model metrics for this module (score, risks, recommendation)."""
    return registry.model_info(
        ["sub_score", "sub_delay", "sub_breach", "sub_reco"])


@router.get("/{vendor_id}")
def scorecard(vendor_id: str, db: Session = Depends(get_db)):
    """Performance scorecard for a single subcontractor."""
    row = db.get(Subcontractor, vendor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    result = ai.evaluate(row)
    # attach raw context
    result["contract_value"] = float(row.contract_value or 0)
    result["delay_days"] = row.delay_days
    result["open_issues"] = row.open_issues
    result["engineer_rating"] = float(row.engineer_rating or 0)
    result["client_rating"] = float(row.client_rating or 0)
    return result


@router.get("/{vendor_id}/progress")
def get_progress(vendor_id: str, db: Session = Depends(get_db)):
    """Weekly progress history + trend-based finish/delay forecast (live tracking)."""
    v = db.get(Subcontractor, vendor_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    ups = (db.query(ProgressUpdate)
           .filter(ProgressUpdate.vendor_id == vendor_id)
           .order_by(ProgressUpdate.week_date).all())
    history = [{
        "week_date": u.week_date.isoformat() if u.week_date else None,
        "progress_pct": float(u.progress_pct or 0),
        "delay_days": u.delay_days,
        "open_issues": u.open_issues,
        "note": u.note,
    } for u in ups]
    fc = tracking.forecast(
        [{"week_date": u.week_date, "progress_pct": u.progress_pct} for u in ups],
        planned_progress=float(v.planned_progress or 0),
    )
    return {"vendor": v.vendor_name, "trade": v.trade, "project": v.project,
            "planned_progress": float(v.planned_progress or 0),
            "history": history, "forecast": fc}


@router.post("/{vendor_id}/progress")
def add_progress(vendor_id: str, payload: dict = Body(...),
                 db: Session = Depends(get_db)):
    """Log this week's progress; also updates the vendor's current state so the
    AI models immediately reflect the latest reality."""
    v = db.get(Subcontractor, vendor_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    wk = payload.get("week_date")
    week_date = dt.date.fromisoformat(wk) if wk else dt.date.today()
    pct = payload.get("progress_pct")
    delay = payload.get("delay_days")
    issues = payload.get("open_issues")
    db.add(ProgressUpdate(
        vendor_id=vendor_id, week_date=week_date,
        progress_pct=pct if pct not in (None, "") else None,
        delay_days=int(delay) if delay not in (None, "") else None,
        open_issues=int(issues) if issues not in (None, "") else None,
        note=payload.get("note"),
    ))
    # Roll the latest values onto the vendor so every AI output updates.
    if pct not in (None, ""):
        v.actual_progress = pct
    if delay not in (None, ""):
        v.delay_days = int(delay)
    if issues not in (None, ""):
        v.open_issues = int(issues)
    db.commit()
    return {"ok": True}


@router.delete("/{vendor_id}")
def delete_vendor(vendor_id: str, db: Session = Depends(get_db)):
    """Remove a subcontractor."""
    obj = db.get(Subcontractor, vendor_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    db.delete(obj)
    db.commit()
    return {"deleted": vendor_id}
