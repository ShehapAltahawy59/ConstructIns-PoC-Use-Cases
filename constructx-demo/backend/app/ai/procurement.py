"""Procurement engine — derive inventory & supplier performance from real
purchase-order / delivery history (never typed).

  * Stock (per project+material)   = delivered − consumed
  * Supplier lead time             = avg(received − order) across deliveries
  * Supplier on-time reliability   = on-time deliveries ÷ total deliveries
  * Open (on-order) qty            = ordered − received on open POs
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def supplier_performance(deliveries: list[Any]) -> dict[str, dict]:
    """Per-supplier lead time, on-time %, delivery count and defect rate from GRN
    history. `deliveries` items must carry .supplier_id (attach before calling)."""
    agg: dict[str, dict] = defaultdict(
        lambda: {"leads": [], "on_time": 0, "total": 0,
                 "received": 0.0, "rejected": 0.0})
    for d in deliveries:
        if not d.received_date or not d.order_date:
            continue
        s = agg[d.supplier_id]
        s["leads"].append((d.received_date - d.order_date).days)
        s["total"] += 1
        s["received"] += _f(d.qty_received)
        s["rejected"] += _f(getattr(d, "qty_rejected", 0))
        if d.expected_date and d.received_date <= d.expected_date:
            s["on_time"] += 1
    out = {}
    for sid, s in agg.items():
        n = s["total"] or 1
        rec = s["received"] or 1
        out[sid] = {
            "avg_lead_time": round(sum(s["leads"]) / len(s["leads"]), 1)
            if s["leads"] else None,
            "reliability": round(s["on_time"] / n * 100, 1),
            "deliveries": s["total"],
            "defect_rate": round(s["rejected"] / rec * 100, 1),
        }
    return out


def stock_by_req(deliveries: list[Any], requirements: list[Any]) \
        -> dict[str, float]:
    """Current stock per (project_id, material_id) = delivered − consumed."""
    delivered: dict[tuple, float] = defaultdict(float)
    for d in deliveries:                     # accepted = received − rejected
        delivered[(d.project_id, d.material_id)] += (
            _f(d.qty_received) - _f(getattr(d, "qty_rejected", 0)))
    stock = {}
    for r in requirements:
        key = (r.project_id, r.material_id)
        stock[r.req_id] = max(0.0, delivered[key] - _f(r.consumed_qty))
    return stock


def on_order_by_req(po_lines: list[Any], pos: dict[str, Any],
                    deliveries: list[Any], requirements: list[Any]) \
        -> dict[str, float]:
    """Qty still on order (ordered − received) for each requirement."""
    ordered: dict[tuple, float] = defaultdict(float)
    for l in po_lines:
        po = pos.get(l.po_id)
        if po and po.status != "Closed":
            ordered[(po.project_id, l.material_id)] += _f(l.qty_ordered)
    received: dict[tuple, float] = defaultdict(float)
    for d in deliveries:
        received[(d.project_id, d.material_id)] += _f(d.qty_received)
    out = {}
    for r in requirements:
        key = (r.project_id, r.material_id)
        out[r.req_id] = max(0.0, ordered[key] - received[key])
    return out
