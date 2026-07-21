"""Earned Value Management for a subcontract (Procore/EVM style).

Planned % is read from the baseline schedule (start → planned end) at a given
date — the Planned Value S-curve. Actual % is the Schedule-of-Values-weighted
% complete from progress claims. From those we derive PV, EV, SPI and billing.
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def planned_percent(start: dt.date | None, end: dt.date | None,
                    as_of: dt.date | None = None) -> float:
    """Baseline planned % complete at `as_of` (linear PV curve, clamped 0-100)."""
    if not start or not end:
        return 0.0
    as_of = as_of or dt.date.today()
    span = (end - start).days
    if span <= 0:
        return 100.0
    frac = (as_of - start).days / span
    return round(max(0.0, min(1.0, frac)) * 100.0, 1)


def contract_value(sov_lines: list[Any]) -> float:
    """Total scheduled value = sum of the SOV line items (the contract sum)."""
    return round(sum(_f(l.scheduled_value) for l in sov_lines), 2)


def actual_percent(sov_lines: list[Any]) -> float:
    """SOV-weighted % complete = sum(value*pct) / sum(value)."""
    total = sum(_f(l.scheduled_value) for l in sov_lines)
    if total <= 0:
        return 0.0
    done = sum(_f(l.scheduled_value) * _f(l.percent_complete) / 100.0
               for l in sov_lines)
    return round(done / total * 100.0, 1)


def metrics(subcontract: Any, sov_lines: list[Any],
            as_of: dt.date | None = None) -> dict:
    """Full EVM snapshot for one subcontract."""
    cv = contract_value(sov_lines)
    planned = planned_percent(subcontract.start_date,
                              subcontract.planned_end_date, as_of)
    actual = actual_percent(sov_lines)
    pv = round(cv * planned / 100.0, 2)          # Planned Value
    ev = round(cv * actual / 100.0, 2)           # Earned Value
    spi = round(ev / pv, 2) if pv > 0 else None  # Schedule Perf Index
    retainage = _f(subcontract.retainage_pct)
    released = _f(getattr(subcontract, "retainage_released", 0))
    billed = ev                                   # progress billing = work done
    held = round(billed * retainage / 100.0, 2)
    retained = round(max(0.0, held - released), 2)
    net_paid = round(billed - retained, 2)
    return {
        "contract_value": cv,
        "planned_progress": planned,
        "actual_progress": actual,
        "planned_value": pv,
        "earned_value": ev,
        "spi": spi,
        "schedule_variance_pct": round(actual - planned, 1),
        "billed_to_date": billed,
        "retainage_pct": retainage,
        "retainage_held": held,
        "retainage_released": round(released, 2),
        "retained": retained,
        "net_paid": net_paid,
    }
