"""AI engine for the Subcontractor module (Project → Assignment → Company model).

Each ASSIGNMENT (a subcontractor's contract on one project) is scored by the
trained models — AI score, delay risk, breach risk. Those are then rolled up to
the COMPANY level (a subcontractor working several projects) for the main
ranking, including workload/capacity across its active assignments.

Engineer/Client ratings were removed (subjective, rarely collected). Cost uses
an earned-value overrun (paid vs the value of work actually completed).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..ml import registry

_RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_kpis(a: Any) -> dict[str, float]:
    """Normalized KPIs (0-100) for one assignment, plus earned-value overrun."""
    quality = _f(a.quality_score)
    inspection = _f(a.inspection_pass)
    planned = _f(a.planned_progress)
    actual = _f(a.actual_progress)
    delay_days = _f(a.delay_days)
    safety = _f(a.safety_score)
    contract = _f(a.contract_value)
    paid = _f(a.paid_amount)

    quality_kpi = _clamp(0.7 * quality + 0.3 * inspection)
    progress_ratio = (actual / planned * 100.0) if planned else 100.0
    schedule_kpi = _clamp(progress_ratio - delay_days * 2.0)

    # Earned-value cost control: paid vs value of work actually done.
    earned = actual / 100.0 * contract
    overrun_pct = ((paid - earned) / earned * 100.0) if earned > 0 else 0.0
    cost_kpi = _clamp(100.0 - max(0.0, overrun_pct))
    safety_kpi = _clamp(safety)

    return {
        "quality": round(quality_kpi, 1),
        "schedule": round(schedule_kpi, 1),
        "cost": round(cost_kpi, 1),
        "safety": round(safety_kpi, 1),
        "overrun_pct": round(overrun_pct, 1),
    }


def data_completeness(a: Any) -> dict[str, Any]:
    """An assignment is only 'evaluable' once it has a quality signal AND work
    has started — so a freshly-planned assignment isn't scored as if it failed."""
    signals = {
        "quality": _f(a.quality_score) > 0,
        "safety": _f(a.safety_score) > 0,
        "progress": _f(a.actual_progress) > 0,
        "financials": _f(a.invoice_amount) > 0,
    }
    present = sum(signals.values())
    return {"signals_present": present, "signals_total": len(signals),
            "evaluable": signals["quality"] and signals["progress"]}


UNRATED = {
    "ai_score": None,
    "delay_risk": "—",
    "contract_breach_risk": "—",
    "recommendation": "New — collecting data",
}


def _features(a: Any, kpis: dict[str, float]) -> dict[str, float]:
    """Feature vector for the trained models (must match datagen.SUB_FEATURES)."""
    planned = _f(a.planned_progress)
    actual = _f(a.actual_progress)
    return {
        "planned_progress": planned,
        "actual_progress": actual,
        "schedule_slip": planned - actual,
        "quality_score": _f(a.quality_score),
        "safety_score": _f(a.safety_score),
        "inspection_pass": _f(a.inspection_pass),
        "delay_days": _f(a.delay_days),
        "open_issues": _f(a.open_issues),
        "contract_value": _f(a.contract_value),
        "invoice_amount": _f(a.invoice_amount),
        "paid_amount": _f(a.paid_amount),
        "overrun_pct": kpis["overrun_pct"],
    }


def _company_recommendation(avg: float, d_risk: str, b_risk: str,
                            capacity_status: str) -> str:
    if capacity_status == "Overloaded" and avg >= 65 and b_risk != "High":
        return "Top Performer — At Capacity"
    if avg >= 90 and d_risk == "Low" and b_risk == "Low":
        return "Preferred Vendor"
    if avg >= 80 and b_risk != "High":
        return "Monitor"
    if avg >= 65:
        return "Monitor Closely"
    return "Do Not Assign New Projects"


def _worst(risks: list[str]) -> str:
    valid = [r for r in risks if r in _RISK_ORDER]
    return max(valid, key=lambda r: _RISK_ORDER[r]) if valid else "—"


# ---- Assignment-level evaluation ---------------------------------------------
def evaluate_all_assignments(items: list[Any]) -> list[dict[str, Any]]:
    """Score every assignment (batched). `items` are assignment objects enriched
    with .company_name, .trade, .project_name and .utilization (company load)."""
    if not items:
        return []
    kpis_list = [compute_kpis(a) for a in items]
    feats = [_features(a, k) for a, k in zip(items, kpis_list)]
    reco_feats = [{**f, "utilization": _f(getattr(a, "utilization", 0))}
                  for f, a in zip(feats, items)]

    scores = registry.predict_sub_score_batch(feats)
    delays = registry.predict_sub_delay_batch(feats)
    breaches = registry.predict_sub_breach_batch(feats)
    recos = registry.predict_sub_reco_batch(reco_feats)
    comp = [data_completeness(a) for a in items]

    out = []
    for a, k, sc, dr, br, rc, c in zip(
            items, kpis_list, scores, delays, breaches, recos, comp):
        item = {
            "subcontract_id": a.subcontract_id,
            "vendor_id": a.vendor_id,
            "company": getattr(a, "company_name", ""),
            "trade": getattr(a, "trade", ""),
            "project_id": a.project_id,
            "project": getattr(a, "project_name", ""),
            "contract_value": _f(a.contract_value),
            "planned_progress": _f(a.planned_progress),
            "actual_progress": _f(a.actual_progress),
            "quality_score": _f(a.quality_score),
            "safety_score": _f(a.safety_score),
            "inspection_pass": _f(a.inspection_pass),
            "delay_days": _f(a.delay_days),
            "open_issues": _f(a.open_issues),
            "invoice_amount": _f(a.invoice_amount),
            "paid_amount": _f(a.paid_amount),
            "kpis": k,
            "ai_score": sc,
            "delay_risk": dr,
            "contract_breach_risk": br,
            "recommendation": rc,
            "evaluable": c["evaluable"],
            "data_completeness": f"{c['signals_present']}/{c['signals_total']}",
        }
        if not c["evaluable"]:
            item.update(UNRATED)
        out.append(item)
    return out


# ---- Company-level rollup (the main ranking) ---------------------------------
def aggregate_companies(assign_evals: list[dict], companies: list[Any]) \
        -> list[dict[str, Any]]:
    by_vendor: dict[str, list] = defaultdict(list)
    for e in assign_evals:
        by_vendor[e["vendor_id"]].append(e)

    results = []
    for c in companies:
        evs = by_vendor.get(c.vendor_id, [])
        rated = [e for e in evs if e["evaluable"]]
        active = len(evs)
        cap = int(c.capacity_projects or 0)
        util = round(active / cap * 100) if cap else 0
        cap_status = ("Overloaded" if util > 100
                      else "Near Capacity" if util >= 85 else "Available")

        if rated:
            avg = round(sum(e["ai_score"] for e in rated) / len(rated), 1)
            d_risk = _worst([e["delay_risk"] for e in rated])
            b_risk = _worst([e["contract_breach_risk"] for e in rated])
            reco = _company_recommendation(avg, d_risk, b_risk, cap_status)
            evaluable = True
        else:
            avg, d_risk, b_risk = None, "—", "—"
            reco = "New — collecting data"
            evaluable = False

        results.append({
            "vendor_id": c.vendor_id,
            "company": c.company_name,
            "trade": c.trade,
            "projects": active,
            "capacity_projects": cap,
            "utilization": util,
            "capacity_status": cap_status,
            "avg_score": avg,
            "delay_risk": d_risk,
            "contract_breach_risk": b_risk,
            "recommendation": reco,
            "evaluable": evaluable,
        })

    rated = [r for r in results if r["evaluable"]]
    unrated = [r for r in results if not r["evaluable"]]
    rated.sort(key=lambda r: r["avg_score"], reverse=True)
    for rank, r in enumerate(rated, start=1):
        r["rank"] = rank
    for r in unrated:
        r["rank"] = None
    return rated + unrated
