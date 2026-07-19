"""Scoring layer: derive the 'score' inputs from raw operational records.

In reality a company doesn't store a tidy 'Quality Score = 95'. It stores raw
records — inspection results, NCRs, safety incidents, man-hours, delivery dates.
This module converts those raw records into the normalized scores the AI models
consume, using standard construction-industry methods (first-pass rate, TRIR,
on-time-delivery rate, average lead time).
"""
from __future__ import annotations

from typing import Any


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ---- Subcontractor scores -----------------------------------------------------
def quality_and_inspection(inspections_total, inspections_passed,
                           ncrs_raised=0, ncrs_closed=0) -> dict:
    """Quality Score + Inspection Pass % from QA/QC records.

    Inspection Pass %  = passed inspections / total inspections
    NCR closure rate   = NCRs closed / NCRs raised
    Quality Score      = 0.7 * inspection-pass + 0.3 * NCR-closure
    """
    total = _num(inspections_total)
    passed = _num(inspections_passed)
    raised = _num(ncrs_raised)
    closed = _num(ncrs_closed)

    inspection_pass = passed / total * 100 if total > 0 else None
    ncr_closure = 100.0 if raised <= 0 else closed / raised * 100
    quality = (0.7 * inspection_pass + 0.3 * ncr_closure
               if inspection_pass is not None else None)

    return {
        "inspection_pass": round(inspection_pass, 1)
        if inspection_pass is not None else None,
        "ncr_closure_rate": round(ncr_closure, 1),
        "quality_score": round(_clip(quality), 1)
        if quality is not None else None,
        "explain": (
            f"Inspection Pass = {int(passed)}/{int(total)} = "
            f"{inspection_pass:.1f}%; NCR closure = {ncr_closure:.0f}%; "
            f"Quality = 0.7×{inspection_pass:.1f} + 0.3×{ncr_closure:.0f} "
            f"= {_clip(quality):.1f}"
        ) if inspection_pass is not None else "No inspections recorded",
    }


def safety(recordable_incidents, man_hours) -> dict:
    """Safety Score from the incident log using the OSHA TRIR standard.

    TRIR = (recordable incidents × 200,000) / total man-hours
           (200,000 = 100 workers × 2,000 hrs/yr)
    Safety Score = 100 − TRIR × 10   (0 incidents → 100; TRIR 10 → 0)
    """
    incidents = _num(recordable_incidents)
    hours = _num(man_hours)
    if hours <= 0:
        return {"safety_score": None, "trir": None,
                "explain": "No man-hours recorded"}
    trir = incidents * 200_000 / hours
    score = _clip(100 - trir * 10)
    return {
        "safety_score": round(score, 1),
        "trir": round(trir, 2),
        "explain": (
            f"TRIR = {int(incidents)}×200,000 / {int(hours):,} = {trir:.2f}; "
            f"Safety = 100 − {trir:.2f}×10 = {score:.1f}"
        ),
    }


# ---- Material / supplier scores ----------------------------------------------
def delivery_reliability(deliveries_total, deliveries_on_time) -> dict:
    """Delivery Reliability % from goods-receipt vs promised dates."""
    total = _num(deliveries_total)
    on_time = _num(deliveries_on_time)
    if total <= 0:
        return {"delivery_reliability": None,
                "explain": "No deliveries recorded"}
    rel = on_time / total * 100
    return {
        "delivery_reliability": round(rel, 1),
        "explain": (
            f"On-time = {int(on_time)}/{int(total)} = {rel:.1f}%"
        ),
    }


def average_lead_time(lead_days) -> dict:
    """Average Lead Time (days) from past order→receipt durations."""
    if isinstance(lead_days, str):
        parts = [p.strip() for p in lead_days.replace(";", ",").split(",")]
        vals = [_num(p) for p in parts if p]
    else:
        vals = [_num(x) for x in (lead_days or []) if x not in (None, "")]
    vals = [v for v in vals if v > 0]
    if not vals:
        return {"lead_time_days": None, "explain": "No lead times recorded"}
    avg = sum(vals) / len(vals)
    return {
        "lead_time_days": round(avg, 1),
        "explain": (
            f"Average of {len(vals)} deliveries "
            f"({'+'.join(str(int(v)) for v in vals)}) / {len(vals)} "
            f"= {avg:.1f} days"
        ),
    }
