"""AI engine for the Material Management & Supplier Tracking module.

Implements the use-case spec:
  - Demand forecasting
  - Inventory health / stock-status analysis
  - Supplier performance scoring + ranking
  - Supplier delivery-delay prediction
  - Reorder / purchase recommendations

Transparent rule/scoring engines keep the demo reproducible. In production these
slots map to the suggested models: Demand Forecasting (RF/XGBoost), Supplier
Scoring, Delay Prediction, and a Recommendation Engine.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..ml import registry


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _demand_features(row: Any) -> dict[str, float]:
    return {
        "current_stock": _f(row.current_stock),
        "minimum_stock": _f(row.minimum_stock),
        "required_qty": _f(row.required_qty),
        "lead_time_days": _f(row.lead_time_days),
        "unit_price": _f(row.unit_price),
        "delivery_reliability": _f(row.delivery_reliability, 100.0),
    }


def _delay_features(row: Any) -> dict[str, float]:
    return {
        "lead_time_days": _f(row.lead_time_days),
        "delivery_reliability": _f(row.delivery_reliability, 100.0),
        "required_qty": _f(row.required_qty),
        "unit_price": _f(row.unit_price),
    }


def demand_forecast(row: Any) -> int:
    """Projected demand for the upcoming cycle (trained RandomForestRegressor)."""
    return registry.predict_material_demand(_demand_features(row))


def stock_status(row: Any) -> str:
    """Inventory-health classification against the reorder point (minimum stock).

    Standard inventory management judges health by how far current stock sits
    above the safety/minimum level, not against the full project BOQ (which is
    consumed over the whole project). Below minimum is critical.
    """
    current = _f(row.current_stock)
    minimum = _f(row.minimum_stock)
    ratio = (current / minimum) if minimum else 2.5

    if current < minimum:
        return "Critical"
    if ratio < 1.5:
        return "Low Stock"
    if ratio < 2.5:
        return "Medium"
    return "Healthy"


ACTION_BY_STATUS = {
    "Critical": "Urgent Purchase",
    "Low Stock": "Reorder Now",
    "Medium": "Schedule Purchase",
    "Healthy": "No Action",
}


def reorder_qty(row: Any, forecast: int) -> int:
    """Optimal reorder quantity (trained RandomForestRegressor)."""
    return registry.predict_material_reorder(_demand_features(row))


def delivery_delay_risk(row: Any) -> str:
    """Predict supplier delivery-delay risk (trained RandomForestClassifier)."""
    return registry.predict_material_delay(_delay_features(row))


def supplier_scores(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """Score + rank every supplier with the trained supplier-performance model.

    The model predicts a 0-100 performance outcome from delivery reliability,
    lead time and within-category price percentile. Each supplier's rows are
    scored, then averaged into an overall supplier score.
    """
    # Category price ranges to derive each row's price percentile (0=cheapest).
    cat_prices: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        cat_prices[r.category].append(_f(r.unit_price))
    cat_bounds = {c: (min(p), max(p)) for c, p in cat_prices.items() if p}

    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"scores": [], "reliability": [], "lead": [],
                 "categories": set(), "materials": 0})
    for r in rows:
        lo, hi = cat_bounds.get(r.category, (0.0, 0.0))
        price_pct = (_f(r.unit_price) - lo) / (hi - lo) if hi > lo else 0.0
        model_score = registry.predict_supplier_score({
            "delivery_reliability": _f(r.delivery_reliability, 100.0),
            "lead_time_days": _f(r.lead_time_days),
            "price_percentile": price_pct,
        })
        s = agg[r.supplier]
        s["scores"].append(model_score)
        s["reliability"].append(_f(r.delivery_reliability, 100.0))
        s["lead"].append(_f(r.lead_time_days))
        s["categories"].add(r.category)
        s["materials"] += 1

    scores: dict[str, dict[str, Any]] = {}
    for supplier, s in agg.items():
        scores[supplier] = {
            "supplier": supplier,
            "score": round(sum(s["scores"]) / len(s["scores"]), 1),
            "avg_reliability": round(sum(s["reliability"]) / len(s["reliability"]), 1),
            "avg_lead_time": round(sum(s["lead"]) / len(s["lead"]), 1),
            "categories": sorted(s["categories"]),
            "materials_supplied": s["materials"],
        }

    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return {item["supplier"]: item for item in ranked}


def best_supplier_for(row: Any, sup_scores: dict[str, dict[str, Any]],
                      rows: list[Any]) -> str:
    """Recommend the highest-scoring supplier able to serve this category."""
    category = row.category
    candidates = {
        r.supplier for r in rows if r.category == category
    }
    ranked = [
        sup_scores[s] for s in candidates if s in sup_scores
    ]
    if not ranked:
        return row.supplier
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[0]["supplier"]


def evaluate_all(rows: list[Any]) -> list[dict[str, Any]]:
    """Full per-material evaluation for the inventory dashboard."""
    sup_scores = supplier_scores(rows)
    results = []
    for r in rows:
        forecast = demand_forecast(r)
        status = stock_status(r)
        action = ACTION_BY_STATUS[status]
        reorder = 0 if action == "No Action" else reorder_qty(r, forecast)
        results.append({
            "material_id": r.material_id,
            "material": r.material_name,
            "category": r.category,
            "project": r.project,
            "current_stock": _f(r.current_stock),
            "minimum_stock": _f(r.minimum_stock),
            "required_qty": _f(r.required_qty),
            "current_supplier": r.supplier,
            "demand_forecast": forecast,
            "stock_status": status,
            "recommended_action": action,
            "reorder_qty": reorder,
            "best_supplier": best_supplier_for(r, sup_scores, rows),
            "delay_risk": delivery_delay_risk(r),
            "expected_delivery": (
                r.expected_delivery.isoformat() if r.expected_delivery else None
            ),
        })
    return results
