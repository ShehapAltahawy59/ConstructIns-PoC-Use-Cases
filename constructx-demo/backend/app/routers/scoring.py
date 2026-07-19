"""Scoring-layer API: turn raw operational records into the derived scores."""
from fastapi import APIRouter, Body

from .. import scoring

router = APIRouter(prefix="/api/scoring", tags=["Scoring Layer"])


@router.post("/subcontractor")
def score_subcontractor(payload: dict = Body(...)):
    """Compute Quality / Inspection / Safety scores from raw QA & safety records.

    Body (all optional): inspections_total, inspections_passed, ncrs_raised,
    ncrs_closed, recordable_incidents, man_hours.
    """
    q = scoring.quality_and_inspection(
        payload.get("inspections_total", 0),
        payload.get("inspections_passed", 0),
        payload.get("ncrs_raised", 0),
        payload.get("ncrs_closed", 0),
    )
    s = scoring.safety(
        payload.get("recordable_incidents", 0),
        payload.get("man_hours", 0),
    )
    return {
        "quality_score": q["quality_score"],
        "inspection_pass": q["inspection_pass"],
        "safety_score": s["safety_score"],
        "detail": {
            "quality": q["explain"],
            "safety": s["explain"],
            "trir": s["trir"],
            "ncr_closure_rate": q["ncr_closure_rate"],
        },
    }


@router.post("/material")
def score_material(payload: dict = Body(...)):
    """Compute Delivery Reliability % and Lead Time from raw delivery records.

    Body (all optional): deliveries_total, deliveries_on_time, lead_days
    (list or comma-separated string of past order→receipt durations).
    """
    rel = scoring.delivery_reliability(
        payload.get("deliveries_total", 0),
        payload.get("deliveries_on_time", 0),
    )
    lead = scoring.average_lead_time(payload.get("lead_days", []))
    return {
        "delivery_reliability": rel["delivery_reliability"],
        "lead_time_days": lead["lead_time_days"],
        "detail": {
            "reliability": rel["explain"],
            "lead_time": lead["explain"],
        },
    }
