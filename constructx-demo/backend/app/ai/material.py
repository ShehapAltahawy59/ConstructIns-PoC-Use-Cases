"""AI engine for Material procurement (project-connected).

Operates on per-project material REQUIREMENTS enriched with derived values
(stock from deliveries, supplier lead time / reliability from GRN history). The
trained models forecast demand, optimal reorder qty and delivery-delay risk;
suppliers are scored on their real performance.
"""
from __future__ import annotations

from typing import Any

from ..ml import registry

ACTION_BY_STATUS = {
    "Critical": "Urgent Purchase",
    "Low Stock": "Reorder Now",
    "Medium": "Schedule Purchase",
    "Healthy": "No Action",
}


def stock_status(current: float, minimum: float, required: float) -> str:
    coverage = (current / required) if required else 1.0
    if current < minimum:
        return "Critical"
    if coverage < 0.75:
        return "Low Stock"
    if coverage < 1.0:
        return "Medium"
    return "Healthy"


def evaluate_all(items: list[dict], best_supplier_by_cat: dict | None = None) \
        -> list[dict]:
    """Evaluate every requirement (batched ML). `items` are enriched dicts."""
    if not items:
        return []
    best_supplier_by_cat = best_supplier_by_cat or {}
    dfeat = [{"current_stock": i["current_stock"], "minimum_stock": i["minimum_stock"],
              "required_qty": i["required_qty"], "lead_time_days": i["lead_time_days"],
              "unit_price": i["unit_price"], "delivery_reliability": i["delivery_reliability"]}
             for i in items]
    lfeat = [{"lead_time_days": i["lead_time_days"], "delivery_reliability": i["delivery_reliability"],
              "required_qty": i["required_qty"], "unit_price": i["unit_price"]}
             for i in items]

    forecasts = registry.predict_material_demand_batch(dfeat)
    reorders = registry.predict_material_reorder_batch(dfeat)
    delays = registry.predict_material_delay_batch(lfeat)

    out = []
    for i, fc, ro, dl in zip(items, forecasts, reorders, delays):
        status = stock_status(i["current_stock"], i["minimum_stock"], i["required_qty"])
        action = ACTION_BY_STATUS[status]
        on_order = int(i.get("on_order", 0))
        need = max(0, ro - on_order)             # already-ordered qty reduces reorder
        out.append({
            **i,
            "demand_forecast": fc,
            "stock_status": status,
            "recommended_action": "On Order" if action != "No Action" and need == 0
            and on_order > 0 else action,
            "reorder_qty": 0 if action == "No Action" else need,
            "delay_risk": dl,
            "best_supplier": best_supplier_by_cat.get(i["category"], i.get("supplier", "")),
        })
    return out


def supplier_scores(supplier_rows: list[dict]) -> list[dict]:
    """Score + rank suppliers with the trained model on their derived performance."""
    if not supplier_rows:
        return []
    feats = [{"delivery_reliability": s["reliability"],
              "lead_time_days": s["avg_lead_time"] if s["avg_lead_time"] else 15,
              "price_percentile": s.get("price_percentile", 0.5)}
             for s in supplier_rows]
    scores = registry.predict_supplier_score_batch(feats)
    ranked = []
    for s, sc in zip(supplier_rows, scores):
        # defective deliveries drag the score down (2 pts per 1% defect rate).
        penalty = min(30.0, s.get("defect_rate", 0) * 2.0)
        ranked.append({**s, "score": round(max(0.0, sc - penalty), 1)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    for rank, s in enumerate(ranked, start=1):
        s["rank"] = rank
    return ranked
