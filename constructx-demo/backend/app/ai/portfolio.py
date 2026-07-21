"""Portfolio-level analytics for the Subcontractor module.

  * Vendor concentration / "monopoly" risk per trade  (HHI over contract value)
  * Workforce capacity summary  (derived from the company rollup)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def concentration_by_trade(assignments: list[Any],
                           company_by_id: dict[str, Any]) -> list[dict]:
    """Per-trade concentration of contract value across companies (HHI).

    HHI = sum(company share^2) * 10000.  <1500 diverse, >=2500 concentrated.
    """
    trades: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for a in assignments:
        comp = company_by_id.get(a.vendor_id)
        if not comp:
            continue
        trades[comp.trade][comp.company_name] += _f(a.contract_value)

    out = []
    for trade, comps in trades.items():
        total = sum(comps.values())
        if total <= 0:
            continue
        shares = {name: v / total for name, v in comps.items()}
        hhi = round(sum(s * s for s in shares.values()) * 10000, 0)
        top_name, top_share = max(shares.items(), key=lambda kv: kv[1])
        risk = ("High" if hhi >= 2500 or top_share >= 0.6
                else "Medium" if hhi >= 1500 or top_share >= 0.45 else "Low")
        out.append({
            "trade": trade,
            "vendor_count": len(comps),
            "total_value": round(total, 0),
            "hhi": hhi,
            "top_vendor": top_name,
            "top_vendor_share": round(top_share * 100, 1),
            "concentration_risk": risk,
        })
    out.sort(key=lambda x: x["hhi"], reverse=True)
    return out


def concentration_summary(assignments, company_by_id) -> dict:
    trades = concentration_by_trade(assignments, company_by_id)
    high = [t for t in trades if t["concentration_risk"] == "High"]
    return {
        "trades_analyzed": len(trades),
        "high_concentration_trades": len(high),
        "single_vendor_trades": sum(1 for t in trades if t["vendor_count"] == 1),
        "riskiest_trade": high[0]["trade"] if high else None,
    }


def capacity_summary(company_rollup: list[dict]) -> dict:
    overloaded = [c for c in company_rollup
                  if c["capacity_status"] == "Overloaded"]
    return {
        "overloaded_vendors": len(overloaded),
        "near_capacity_vendors": sum(
            1 for c in company_rollup
            if c["capacity_status"] == "Near Capacity"),
        "available_vendors": sum(
            1 for c in company_rollup if c["capacity_status"] == "Available"),
        "most_overloaded": overloaded[0]["company"] if overloaded else None,
    }


def capacity_list(company_rollup: list[dict]) -> list[dict]:
    """Companies sorted by workload (most loaded first)."""
    rows = [{
        "vendor": c["company"], "trade": c["trade"],
        "active_projects": c["projects"],
        "capacity_projects": c["capacity_projects"],
        "utilization": c["utilization"],
        "capacity_status": c["capacity_status"],
    } for c in company_rollup]
    rows.sort(key=lambda x: x["utilization"], reverse=True)
    return rows
