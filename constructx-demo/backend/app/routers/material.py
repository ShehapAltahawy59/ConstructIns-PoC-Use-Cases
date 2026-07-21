"""Module 2 API — material procurement (Project → PO → Delivery), with stock and
supplier performance derived from real purchase-order / delivery history."""
import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import cache, import_workbook
from ..ai import material as ai
from ..ai import procurement
from ..database import get_db
from ..models import (
    Delivery, Invoice, Material, MaterialRequirement, POLine, Project,
    PurchaseOrder, Supplier,
)

router = APIRouter(prefix="/api/materials", tags=["Material Management"])


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _context(db):
    """Load everything and derive stock, on-order and supplier performance."""
    suppliers = {s.supplier_id: s for s in db.query(Supplier).all()}
    materials = {m.material_id: m for m in db.query(Material).all()}
    projects = {p.project_id: p for p in db.query(Project).all()}
    reqs = db.query(MaterialRequirement).all()
    pos = {p.po_id: p for p in db.query(PurchaseOrder).all()}
    lines = db.query(POLine).all()
    deliveries = db.query(Delivery).all()
    for d in deliveries:                     # attach supplier for perf calc
        po = pos.get(d.po_id)
        d.supplier_id = po.supplier_id if po else None

    perf = procurement.supplier_performance(deliveries)
    stock = procurement.stock_by_req(deliveries, reqs)
    on_order = procurement.on_order_by_req(lines, pos, deliveries, reqs)

    # which supplier serves each (project, material) + its avg price
    price_sum, price_n, sup_of = defaultdict(float), defaultdict(int), {}
    for l in lines:
        po = pos.get(l.po_id)
        if not po:
            continue
        key = (po.project_id, l.material_id)
        price_sum[key] += _f(l.unit_price)
        price_n[key] += 1
        sup_of[key] = po.supplier_id
    return dict(suppliers=suppliers, materials=materials, projects=projects,
                reqs=reqs, pos=pos, lines=lines, deliveries=deliveries, perf=perf,
                stock=stock, on_order=on_order, price_sum=price_sum,
                price_n=price_n, sup_of=sup_of)


def _supplier_rows(ctx):
    """Per-supplier derived performance + price percentile."""
    # avg unit price per supplier for price competitiveness
    sup_price = defaultdict(list)
    for l in ctx["lines"]:
        po = ctx["pos"].get(l.po_id)
        if po:
            sup_price[po.supplier_id].append(_f(l.unit_price))
    avgp = {s: (sum(v) / len(v) if v else 0) for s, v in sup_price.items()}
    lo, hi = (min(avgp.values()), max(avgp.values())) if avgp else (0, 0)
    rows = []
    for sid, s in ctx["suppliers"].items():
        p = ctx["perf"].get(sid, {"avg_lead_time": None, "reliability": 90,
                                  "deliveries": 0, "defect_rate": 0})
        ap = avgp.get(sid, 0)
        pct = (ap - lo) / (hi - lo) if hi > lo else 0.5
        rows.append({"supplier_id": sid, "name": s.name, "category": s.category,
                     "reliability": p["reliability"], "avg_lead_time": p["avg_lead_time"],
                     "deliveries": p["deliveries"], "defect_rate": p.get("defect_rate", 0),
                     "price_percentile": pct})
    return rows


def _inventory(db):
    def build():
        ctx = _context(db)
        sup_rows = ai.supplier_scores(_supplier_rows(ctx))
        best_by_cat = {}
        for s in sup_rows:                          # best supplier per category
            best_by_cat.setdefault(s["category"], s["name"])
        items = []
        for r in ctx["reqs"]:
            key = (r.project_id, r.material_id)
            sid = ctx["sup_of"].get(key)
            p = ctx["perf"].get(sid, {})
            mat = ctx["materials"].get(r.material_id)
            price = (ctx["price_sum"][key] / ctx["price_n"][key]) if ctx["price_n"][key] else 0
            items.append({
                "req_id": r.req_id, "project_id": r.project_id,
                "project": ctx["projects"][r.project_id].name if r.project_id in ctx["projects"] else r.project_id,
                "material_id": r.material_id,
                "material": mat.name if mat else r.material_id,
                "category": mat.category if mat else "",
                "unit": mat.unit if mat else "",
                "current_stock": round(ctx["stock"][r.req_id]),
                "minimum_stock": _f(r.minimum_stock),
                "required_qty": _f(r.required_qty),
                "on_order": round(ctx["on_order"][r.req_id]),
                "supplier": ctx["suppliers"][sid].name if sid in ctx["suppliers"] else "—",
                "lead_time_days": p.get("avg_lead_time") or 12,
                "delivery_reliability": p.get("reliability", 90),
                "unit_price": price,
            })
        return {"items": ai.evaluate_all(items, best_by_cat), "suppliers": sup_rows}
    return cache.cached("mat_inventory", "materials", build)


@router.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    return _inventory(db)["items"]


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db)):
    return _inventory(db)["suppliers"]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    items = _inventory(db)["items"]
    total = len(items)
    if not total:
        return {"total_materials": 0, "status_counts": {}, "critical_items": 0,
                "items_needing_action": 0, "high_delay_risk": 0, "on_order_items": 0,
                "suppliers": 0, "invoice_exceptions": 0}
    status_counts = defaultdict(int)
    for i in items:
        status_counts[i["stock_status"]] += 1
    return {
        "total_materials": total,
        "status_counts": dict(status_counts),
        "critical_items": status_counts.get("Critical", 0),
        "items_needing_action": sum(1 for i in items
                                    if i["recommended_action"] not in ("No Action", "On Order")),
        "high_delay_risk": sum(1 for i in items if i["delay_risk"] == "High"),
        "on_order_items": sum(1 for i in items if i["on_order"] > 0),
        "suppliers": len(_inventory(db)["suppliers"]),
        "invoice_exceptions": db.query(Invoice).filter(
            Invoice.status == "Exception").count(),
    }


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    items = _inventory(db)["items"]
    return {
        "low_stock_alerts": [
            {"material": i["material"], "project": i["project"],
             "stock_status": i["stock_status"],
             "recommended_action": i["recommended_action"],
             "reorder_qty": i["reorder_qty"]}
            for i in items if i["stock_status"] in ("Critical", "Low Stock")],
        "delay_alerts": [
            {"material": i["material"], "current_supplier": i["supplier"],
             "delay_risk": i["delay_risk"]}
            for i in items if i["delay_risk"] in ("Medium", "High")],
    }


@router.get("/{req_id}")
def requirement_detail(req_id: str, db: Session = Depends(get_db)):
    r = db.get(MaterialRequirement, req_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    ctx = _context(db)
    mat = ctx["materials"].get(r.material_id)
    pos = [p for p in ctx["pos"].values()
           if p.project_id == r.project_id]
    lines_by_po = defaultdict(list)
    for l in ctx["lines"]:
        lines_by_po[l.po_id].append(l)
    dels_by_po = defaultdict(list)
    for d in ctx["deliveries"]:
        dels_by_po[d.po_id].append(d)
    invs_by_po = defaultdict(list)
    for iv in db.query(Invoice).all():
        invs_by_po[iv.po_id].append(iv)
    po_out = []
    for p in pos:
        if not any(l.material_id == r.material_id for l in lines_by_po[p.po_id]):
            continue
        match = _three_way(p, lines_by_po[p.po_id], dels_by_po[p.po_id],
                           invs_by_po[p.po_id])
        po_out.append({
            "po_id": p.po_id, "supplier": ctx["suppliers"][p.supplier_id].name
            if p.supplier_id in ctx["suppliers"] else "—",
            "order_date": p.order_date.isoformat() if p.order_date else None,
            "expected_delivery": p.expected_delivery.isoformat() if p.expected_delivery else None,
            "status": p.status,
            "qty_ordered": sum(_f(l.qty_ordered) for l in lines_by_po[p.po_id]
                               if l.material_id == r.material_id),
            "match": match})
    dels = [{"delivery_id": d.delivery_id, "qty_received": _f(d.qty_received),
             "order_date": d.order_date.isoformat() if d.order_date else None,
             "received_date": d.received_date.isoformat() if d.received_date else None,
             "expected_date": d.expected_date.isoformat() if d.expected_date else None,
             "on_time": bool(d.received_date and d.expected_date
                             and d.received_date <= d.expected_date)}
            for d in ctx["deliveries"]
            if d.project_id == r.project_id and d.material_id == r.material_id]
    return {
        "req_id": req_id, "material": mat.name if mat else r.material_id,
        "unit": mat.unit if mat else "", "category": mat.category if mat else "",
        "project": ctx["projects"][r.project_id].name if r.project_id in ctx["projects"] else r.project_id,
        "project_id": r.project_id, "material_id": r.material_id,
        "current_stock": round(ctx["stock"][req_id]),
        "minimum_stock": _f(r.minimum_stock), "required_qty": _f(r.required_qty),
        "consumed_qty": _f(r.consumed_qty), "on_order": round(ctx["on_order"][req_id]),
        "purchase_orders": po_out, "deliveries": dels,
        "suppliers": [{"supplier_id": s.supplier_id, "name": s.name} for s in ctx["suppliers"].values()],
    }


@router.post("/import")
async def import_workbook_data(file: UploadFile = File(...),
                              db: Session = Depends(get_db)):
    """Import a filled Material Procurement workbook (.xlsx) — replaces module data."""
    content = await file.read()
    try:
        counts = import_workbook.import_material(content, db)
    except Exception as exc:                                  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}")
    cache.bump("materials")
    return {"ok": True, "imported": counts}


@router.post("/po")
def create_po(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Raise a purchase order for a material on a project."""
    pid = payload.get("project_id")
    mid = payload.get("material_id")
    sid = payload.get("supplier_id")
    if not (pid and mid and sid):
        raise HTTPException(status_code=400,
                            detail="project_id, material_id, supplier_id required")
    n = db.query(PurchaseOrder).count() + 1
    po_id = f"PO{n:04d}"
    order = payload.get("order_date")
    exp = payload.get("expected_delivery")
    db.add(PurchaseOrder(
        po_id=po_id, supplier_id=sid, project_id=pid,
        order_date=dt.date.fromisoformat(order) if order else dt.date.today(),
        expected_delivery=dt.date.fromisoformat(exp) if exp else None,
        status="Open"))
    db.add(POLine(line_id=f"{po_id}-L1", po_id=po_id, material_id=mid,
                  qty_ordered=_f(payload.get("qty_ordered")),
                  unit_price=_f(payload.get("unit_price"))))
    db.commit()
    cache.bump("materials")
    return {"ok": True, "po_id": po_id}


@router.post("/delivery")
def record_delivery(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Record a goods-receipt (delivery) against a PO → updates stock + performance."""
    po_id = payload.get("po_id")
    po = db.get(PurchaseOrder, po_id) if po_id else None
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    mid = payload.get("material_id")
    n = db.query(Delivery).count() + 1
    recv = payload.get("received_date")
    db.add(Delivery(
        delivery_id=f"D{n:04d}", po_id=po_id, material_id=mid,
        project_id=po.project_id, qty_received=_f(payload.get("qty_received")),
        qty_rejected=_f(payload.get("qty_rejected")),
        order_date=po.order_date, expected_date=po.expected_delivery,
        received_date=dt.date.fromisoformat(recv) if recv else dt.date.today()))
    po.status = "Received"
    db.commit()
    cache.bump("materials")
    return {"ok": True}


def _three_way(po, po_lines, deliveries, invoices):
    """3-way match: PO ordered vs delivered vs invoiced."""
    ordered_qty = sum(_f(l.qty_ordered) for l in po_lines)
    ordered_val = sum(_f(l.qty_ordered) * _f(l.unit_price) for l in po_lines)
    received = sum(_f(d.qty_received) - _f(getattr(d, "qty_rejected", 0))
                   for d in deliveries)
    billed_qty = sum(_f(i.billed_qty) for i in invoices)
    billed_amt = sum(_f(i.amount) for i in invoices)
    if billed_qty == 0:
        status = "No invoice"
    elif billed_qty > received * 1.02:
        status = "Exception: over-billed"
    elif billed_amt > ordered_val * 1.05 and ordered_val > 0:
        status = "Exception: price variance"
    else:
        status = "Matched"
    return {"ordered_qty": round(ordered_qty), "received_qty": round(received),
            "billed_qty": round(billed_qty), "billed_amount": round(billed_amt),
            "match_status": status}


@router.post("/invoice")
def submit_invoice(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Submit a supplier invoice against a PO and run the 3-way match."""
    po_id = payload.get("po_id")
    po = db.get(PurchaseOrder, po_id) if po_id else None
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    lines = db.query(POLine).filter(POLine.po_id == po_id).all()
    dels = db.query(Delivery).filter(Delivery.po_id == po_id).all()
    invs = db.query(Invoice).filter(Invoice.po_id == po_id).all()
    n = db.query(Invoice).count() + 1
    inv = Invoice(
        invoice_id=f"INV{n:04d}", po_id=po_id, supplier_id=po.supplier_id,
        invoice_date=dt.date.today(), billed_qty=_f(payload.get("billed_qty")),
        amount=_f(payload.get("amount")))
    match = _three_way(po, lines, dels, invs + [inv])
    inv.status = "Matched" if match["match_status"] == "Matched" else "Exception"
    db.add(inv)
    db.commit()
    cache.bump("materials")
    return {"ok": True, "invoice_id": inv.invoice_id, "match": match}
