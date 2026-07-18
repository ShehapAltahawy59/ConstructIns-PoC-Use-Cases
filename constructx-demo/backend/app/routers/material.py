"""Module 2 API: AI-Powered Material Management & Supplier Tracking."""
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import ingest
from ..ai import material as ai
from ..database import get_db
from ..ml import registry
from ..models import Material

router = APIRouter(prefix="/api/materials", tags=["Material Management"])


def _all(db: Session):
    return db.query(Material).all()


@router.get("/raw")
def raw_data(db: Session = Depends(get_db)):
    """Raw material / inventory input data."""
    rows = _all(db)
    return [
        {
            "material_id": r.material_id,
            "material_name": r.material_name,
            "category": r.category,
            "current_stock": float(r.current_stock or 0),
            "minimum_stock": float(r.minimum_stock or 0),
            "required_qty": float(r.required_qty or 0),
            "supplier": r.supplier,
            "lead_time_days": r.lead_time_days,
            "unit_price": float(r.unit_price or 0),
            "delivery_reliability": float(r.delivery_reliability or 0),
            "project": r.project,
            "expected_delivery": (
                r.expected_delivery.isoformat() if r.expected_delivery else None
            ),
        }
        for r in rows
    ]


@router.get("/evaluate")
def evaluate(db: Session = Depends(get_db)):
    """AI evaluation for every material (inventory dashboard feed)."""
    return ai.evaluate_all(_all(db))


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db)):
    """Supplier ranking / scoring."""
    scores = ai.supplier_scores(_all(db))
    return sorted(scores.values(), key=lambda x: x["rank"])


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    """Low-stock alerts and supplier delivery-delay alerts."""
    results = ai.evaluate_all(_all(db))
    return {
        "low_stock_alerts": [
            {"material": r["material"], "project": r["project"],
             "stock_status": r["stock_status"],
             "recommended_action": r["recommended_action"],
             "reorder_qty": r["reorder_qty"]}
            for r in results if r["stock_status"] in ("Critical", "Low Stock")
        ],
        "delay_alerts": [
            {"material": r["material"], "current_supplier": r["current_supplier"],
             "delay_risk": r["delay_risk"]}
            for r in results if r["delay_risk"] in ("Medium", "High")
        ],
    }


@router.get("/purchase-recommendations")
def purchase_recommendations(db: Session = Depends(get_db)):
    """Purchase recommendations for materials needing action."""
    results = ai.evaluate_all(_all(db))
    return [
        {
            "material": r["material"],
            "project": r["project"],
            "stock_status": r["stock_status"],
            "recommended_action": r["recommended_action"],
            "reorder_qty": r["reorder_qty"],
            "best_supplier": r["best_supplier"],
            "demand_forecast": r["demand_forecast"],
        }
        for r in results if r["recommended_action"] != "No Action"
    ]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Inventory-dashboard KPI summary."""
    results = ai.evaluate_all(_all(db))
    total = len(results)
    if not total:
        return {"total_materials": 0}
    status_counts: dict[str, int] = {}
    for r in results:
        status_counts[r["stock_status"]] = (
            status_counts.get(r["stock_status"], 0) + 1
        )
    high_delay = sum(1 for r in results if r["delay_risk"] == "High")
    need_action = sum(1 for r in results
                      if r["recommended_action"] != "No Action")
    return {
        "total_materials": total,
        "status_counts": status_counts,
        "critical_items": status_counts.get("Critical", 0),
        "items_needing_action": need_action,
        "high_delay_risk": high_delay,
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
        records, warnings = ingest.rows_to_records(rows, ingest.MAT_SPEC)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not records:
        raise HTTPException(status_code=400,
                            detail="; ".join(warnings) or "No valid rows found")
    result = ingest.upsert(db, Material, ingest.MAT_SPEC, records,
                           replace=(mode == "replace"))
    result["warnings"] = warnings[:20]
    return result


@router.post("")
def add_material(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Add or update a material. New records need a name; existing ones can be
    patched with any subset of fields (for live incremental updates)."""
    rec = ingest.coerce_record(payload, ingest.MAT_SPEC)
    if not rec.get("material_id"):
        raise HTTPException(status_code=400, detail="Material ID is required")
    exists = db.get(Material, rec["material_id"]) is not None
    if not exists and not rec.get("material_name"):
        raise HTTPException(status_code=400,
                            detail="Material Name is required for a new material")
    return {"ok": True, **ingest.upsert(db, Material, ingest.MAT_SPEC, [rec])}


@router.get("/template.csv")
def template():
    """Download a blank CSV template with the correct columns."""
    return PlainTextResponse(
        ingest.template_csv(ingest.MAT_SPEC),
        headers={"Content-Disposition":
                 "attachment; filename=materials_template.csv"},
    )


@router.get("/model-info")
def model_info():
    """Trained-model metrics for this module (demand, reorder, delay, supplier)."""
    return registry.model_info(
        ["mat_demand", "mat_reorder", "mat_delay", "sup_score"])


@router.get("/{material_id}")
def material_detail(material_id: str, db: Session = Depends(get_db)):
    """Detailed AI evaluation for a single material."""
    row = db.get(Material, material_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Material not found")
    # evaluate_all needs the full set for supplier scoring context
    all_rows = _all(db)
    for r in ai.evaluate_all(all_rows):
        if r["material_id"] == material_id:
            return r
    raise HTTPException(status_code=404, detail="Material not found")


@router.delete("/{material_id}")
def delete_material(material_id: str, db: Session = Depends(get_db)):
    """Remove a material."""
    obj = db.get(Material, material_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Material not found")
    db.delete(obj)
    db.commit()
    return {"deleted": material_id}
