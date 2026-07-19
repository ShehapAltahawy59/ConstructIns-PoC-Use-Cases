"""Live project tracking: turn a vendor's weekly progress history into a trend
and a data-driven finish/delay forecast.

Given the progress-% reported each week, we measure the vendor's actual velocity
(% per week) and project when they'll reach 100% at that pace — the core of
"really tracking the live project".
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def forecast(points: list[dict], planned_progress: float | None = None) -> dict:
    """points: [{'week_date': date, 'progress_pct': number}] (any order)."""
    pts = sorted(
        [(p["week_date"], _f(p["progress_pct"])) for p in points
         if p.get("week_date") is not None],
        key=lambda x: x[0],
    )
    if not pts:
        return {"status": "No history", "velocity_per_week": None,
                "weeks_to_finish": None, "projected_completion": None,
                "latest_progress": None, "planned_progress": planned_progress}

    last_d, last_p = pts[-1]
    if len(pts) < 2:
        return {"status": "Insufficient history", "velocity_per_week": None,
                "weeks_to_finish": None, "projected_completion": None,
                "latest_progress": round(last_p, 1),
                "planned_progress": planned_progress}

    first_d, first_p = pts[0]
    weeks = max((last_d - first_d).days / 7.0, 0.1)
    velocity = (last_p - first_p) / weeks          # % per week
    remaining = max(0.0, 100.0 - last_p)

    if velocity > 0.1:
        weeks_to_finish = remaining / velocity
        projected = last_d + dt.timedelta(days=round(weeks_to_finish * 7))
    else:
        weeks_to_finish = None
        projected = None

    if last_p >= 100:
        status = "Complete"
    elif velocity <= 0.1:
        status = "Stalled"
    elif planned_progress is not None and last_p < planned_progress - 5:
        status = "Behind schedule"
    elif planned_progress is not None and last_p >= planned_progress:
        status = "On track"
    else:
        status = "In progress"

    return {
        "status": status,
        "velocity_per_week": round(velocity, 1),
        "weeks_to_finish": round(weeks_to_finish, 1) if weeks_to_finish else None,
        "projected_completion": projected.isoformat() if projected else None,
        "latest_progress": round(last_p, 1),
        "planned_progress": planned_progress,
        "behind_by": (round(planned_progress - last_p, 1)
                      if planned_progress is not None else None),
    }
