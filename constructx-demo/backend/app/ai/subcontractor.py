"""AI engine for the Subcontractor Management module.

Implements the use-case spec:
  - Calculate KPIs (Quality, Cost, Schedule, Safety)
  - Weighted performance scoring
    (Business rules: Quality 35%, Schedule 25%, Cost 20%, Safety 10%, Client 10%)
  - Delay-risk prediction  (heuristic classifier)
  - Contract-breach-risk prediction (heuristic classifier)
  - Ranking + vendor recommendation

The "models" here are transparent rule/weighted-scoring engines so the demo is
fully reproducible without a training step. In production these slots map to the
suggested models: Random Forest Regressor (scoring), RF/XGBoost Classifier
(risk), and a ranking algorithm.
"""
from __future__ import annotations

from typing import Any

from ..ml import registry
from . import portfolio

# Business rules from the use-case document (section 9).
WEIGHTS = {
    "quality": 0.35,
    "schedule": 0.25,
    "cost": 0.20,
    "safety": 0.10,
    "client": 0.10,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_kpis(row: Any) -> dict[str, float]:
    """Return the four normalized KPIs (0-100) plus derived cost overrun."""
    quality_score = _f(row.quality_score)
    inspection = _f(row.inspection_pass)
    planned = _f(row.planned_progress)
    actual = _f(row.actual_progress)
    delay_days = _f(row.delay_days)
    safety = _f(row.safety_score)
    invoice = _f(row.invoice_amount)
    paid = _f(row.paid_amount)

    # Quality KPI: quality score weighted with inspection pass rate.
    quality_kpi = _clamp(0.7 * quality_score + 0.3 * inspection)

    # Schedule KPI: progress ratio penalised by accrued delay days.
    progress_ratio = (actual / planned * 100.0) if planned else 100.0
    schedule_kpi = _clamp(progress_ratio - delay_days * 2.0)

    # Cost KPI: penalise budget overrun (paid above invoiced).
    overrun_pct = ((paid - invoice) / invoice * 100.0) if invoice else 0.0
    cost_kpi = _clamp(100.0 - max(0.0, overrun_pct))

    # Safety KPI: already 0-100.
    safety_kpi = _clamp(safety)

    return {
        "quality": round(quality_kpi, 1),
        "schedule": round(schedule_kpi, 1),
        "cost": round(cost_kpi, 1),
        "safety": round(safety_kpi, 1),
        "overrun_pct": round(overrun_pct, 1),
    }


def performance_score(kpis: dict[str, float], client_rating: float) -> float:
    """Weighted overall score (0-100)."""
    client_kpi = _clamp(client_rating * 20.0)  # 0-5 rating -> 0-100
    score = (
        WEIGHTS["quality"] * kpis["quality"]
        + WEIGHTS["schedule"] * kpis["schedule"]
        + WEIGHTS["cost"] * kpis["cost"]
        + WEIGHTS["safety"] * kpis["safety"]
        + WEIGHTS["client"] * client_kpi
    )
    return round(score, 1)


def _features(row: Any, kpis: dict[str, float]) -> dict[str, float]:
    """Assemble the feature vector consumed by the trained RandomForest models."""
    planned = _f(row.planned_progress)
    actual = _f(row.actual_progress)
    return {
        "planned_progress": planned,
        "actual_progress": actual,
        "schedule_slip": planned - actual,
        "quality_score": _f(row.quality_score),
        "safety_score": _f(row.safety_score),
        "inspection_pass": _f(row.inspection_pass),
        "delay_days": _f(row.delay_days),
        "open_issues": _f(row.open_issues),
        "contract_value": _f(row.contract_value),
        "invoice_amount": _f(row.invoice_amount),
        "paid_amount": _f(row.paid_amount),
        "overrun_pct": kpis["overrun_pct"],
        "engineer_rating": _f(row.engineer_rating),
        "client_rating": _f(row.client_rating),
    }


def delay_risk(row: Any, kpis: dict[str, float]) -> str:
    """Predict delay risk with the trained RandomForestClassifier."""
    return registry.predict_sub_delay(_features(row, kpis))


def breach_risk(row: Any, kpis: dict[str, float]) -> str:
    """Predict contract-breach risk with the trained RandomForestClassifier."""
    return registry.predict_sub_breach(_features(row, kpis))


def recommendation(score: float, d_risk: str, b_risk: str,
                   capacity_status: str = "Available") -> str:
    # A high performer with no spare capacity can't take on new work.
    if capacity_status == "Overloaded" and score >= 65 and b_risk != "High":
        return "Top Performer — At Capacity"
    if score >= 90 and d_risk == "Low" and b_risk == "Low":
        return "Preferred Vendor"
    if score >= 80 and b_risk != "High":
        return "Monitor"
    if score >= 65:
        return "Monitor Closely"
    return "Do Not Assign New Projects"


def evaluate(row: Any) -> dict[str, Any]:
    """Full evaluation for a single subcontractor row."""
    kpis = compute_kpis(row)
    feats = _features(row, kpis)
    cap = portfolio.capacity_for(row)
    # AI Score, risks and recommendation are all trained-model predictions.
    score = registry.predict_sub_score(feats)
    d_risk = registry.predict_sub_delay(feats)
    b_risk = registry.predict_sub_breach(feats)
    reco = registry.predict_sub_reco({**feats, "utilization": cap["utilization"]})
    return {
        "vendor_id": row.vendor_id,
        "vendor": row.vendor_name,
        "trade": row.trade,
        "project": row.project,
        "kpis": kpis,
        "ai_score": score,
        "delay_risk": d_risk,
        "contract_breach_risk": b_risk,
        "capacity_status": cap["capacity_status"],
        "utilization": cap["utilization"],
        "active_projects": cap["active_projects"],
        "capacity_projects": cap["capacity_projects"],
        "recommendation": reco,
    }


def evaluate_all(rows: list[Any]) -> list[dict[str, Any]]:
    """Evaluate and rank every subcontractor (highest score = rank 1)."""
    results = [evaluate(r) for r in rows]
    results.sort(key=lambda r: r["ai_score"], reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return results
