"""Portfolio-level analytics for the Subcontractor Management module.

Covers the two brochure features that per-vendor scoring doesn't:
  * Vendor concentration / "monopoly" risk  -> identify diverse vendors
  * Workforce capacity matching              -> is a subcontractor overloaded?

Concentration uses the Herfindahl-Hirschman Index (HHI), the standard
market-concentration measure used by competition regulators.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---- Vendor concentration / monopoly risk ------------------------------------
def concentration_by_trade(rows: list[Any]) -> list[dict[str, Any]]:
    """Per-trade concentration of spend across vendors.

    HHI = sum(share_i^2) * 10000, where share_i is each vendor's fraction of the
    trade's total contract value.
      HHI < 1500   -> competitive / diverse
      1500-2500    -> moderately concentrated
      >= 2500      -> highly concentrated  (regulator threshold)
    A single dominant vendor (top share) is flagged separately.
    """
    trades: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        trades[r.trade][r.vendor_name] += _f(r.contract_value)

    results = []
    for trade, vendors in trades.items():
        total = sum(vendors.values())
        if total <= 0:
            continue
        shares = {v: val / total for v, val in vendors.items()}
        hhi = round(sum(s * s for s in shares.values()) * 10000, 0)
        top_vendor, top_share = max(shares.items(), key=lambda kv: kv[1])

        if hhi >= 2500 or top_share >= 0.6:
            risk = "High"
        elif hhi >= 1500 or top_share >= 0.45:
            risk = "Medium"
        else:
            risk = "Low"

        results.append({
            "trade": trade,
            "vendor_count": len(vendors),
            "total_value": round(total, 0),
            "hhi": hhi,
            "top_vendor": top_vendor,
            "top_vendor_share": round(top_share * 100, 1),
            "concentration_risk": risk,
        })

    # Most concentrated (riskiest) first.
    results.sort(key=lambda x: x["hhi"], reverse=True)
    return results


def concentration_summary(rows: list[Any]) -> dict[str, Any]:
    trades = concentration_by_trade(rows)
    high = [t for t in trades if t["concentration_risk"] == "High"]
    return {
        "trades_analyzed": len(trades),
        "high_concentration_trades": len(high),
        "single_vendor_trades": sum(1 for t in trades if t["vendor_count"] == 1),
        "riskiest_trade": high[0]["trade"] if high else None,
    }


# ---- Workforce capacity matching ---------------------------------------------
def capacity_status(active: float, capacity: float) -> str:
    if capacity <= 0:
        return "Unknown"
    util = active / capacity
    if util > 1.0:
        return "Overloaded"
    if util >= 0.85:
        return "Near Capacity"
    return "Available"


def capacity_for(row: Any) -> dict[str, Any]:
    active = _f(row.active_projects)
    capacity = _f(row.capacity_projects)
    util = (active / capacity * 100) if capacity else 0.0
    return {
        "active_projects": int(active),
        "capacity_projects": int(capacity),
        "utilization": round(util, 0),
        "capacity_status": capacity_status(active, capacity),
    }


def capacity_analysis(rows: list[Any]) -> list[dict[str, Any]]:
    """Per-vendor workload utilisation, most overloaded first."""
    out = []
    for r in rows:
        cap = capacity_for(r)
        cap["vendor"] = r.vendor_name
        cap["trade"] = r.trade
        out.append(cap)
    out.sort(key=lambda x: x["utilization"], reverse=True)
    return out


def capacity_summary(rows: list[Any]) -> dict[str, Any]:
    analysis = capacity_analysis(rows)
    overloaded = [v for v in analysis if v["capacity_status"] == "Overloaded"]
    return {
        "overloaded_vendors": len(overloaded),
        "near_capacity_vendors": sum(
            1 for v in analysis if v["capacity_status"] == "Near Capacity"),
        "available_vendors": sum(
            1 for v in analysis if v["capacity_status"] == "Available"),
        "most_overloaded": overloaded[0]["vendor"] if overloaded else None,
    }
