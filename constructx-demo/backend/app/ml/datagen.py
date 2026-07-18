"""Synthetic training-data generators for the ConstructX ML models.

The two spec datasets are only 40 rows each — far too small to train on. Here we
generate large, *realistic* datasets whose target variables are produced by a
hidden noisy non-linear process, so the RandomForest models have a genuine
pattern to learn rather than a formula to memorise. Random seeds are fixed for
reproducibility.

Feature ORDER is defined by the *_FEATURES lists and reused at inference time so
training and prediction always agree.
"""
from __future__ import annotations

import numpy as np

# ---- canonical feature orders -------------------------------------------------
SUB_FEATURES = [
    "planned_progress", "actual_progress", "schedule_slip", "quality_score",
    "safety_score", "inspection_pass", "delay_days", "open_issues",
    "contract_value", "invoice_amount", "paid_amount", "overrun_pct",
    "engineer_rating", "client_rating",
]

# Recommendation also needs the vendor's current workload.
SUB_RECO_FEATURES = SUB_FEATURES + ["utilization"]

MAT_DEMAND_FEATURES = [
    "current_stock", "minimum_stock", "required_qty",
    "lead_time_days", "unit_price", "delivery_reliability",
]

MAT_DELAY_FEATURES = [
    "lead_time_days", "delivery_reliability", "required_qty", "unit_price",
]

MAT_REORDER_FEATURES = [
    "current_stock", "minimum_stock", "required_qty",
    "lead_time_days", "delivery_reliability",
]

SUP_FEATURES = ["delivery_reliability", "lead_time_days", "price_percentile"]

RISK_LABELS = {0: "Low", 1: "Medium", 2: "High"}
RISK_CLASSES = ["Low", "Medium", "High"]

# Recommendation classes — index == integer label used below.
RECO_CLASSES = [
    "Do Not Assign New Projects",     # 0
    "Monitor Closely",                # 1
    "Monitor",                        # 2
    "Preferred Vendor",               # 3
    "Top Performer — At Capacity",    # 4
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _clip(x, lo=0.0, hi=100.0):
    return np.clip(x, lo, hi)


def assemble(features: dict, names: list[str]) -> np.ndarray:
    """Stack named feature arrays/values into a 2-D matrix in canonical order."""
    cols = [np.asarray(features[n], dtype=float).reshape(-1) for n in names]
    return np.column_stack(cols)


# ---- Module 1: subcontractors -------------------------------------------------
def generate_subcontractors(n: int = 2500, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)

    # Latent "reliability" trait per vendor drives everything (never a feature).
    reliability = rng.beta(5, 2, n)

    quality = _clip(rng.normal(55 + 40 * reliability, 9, n), 30, 100)
    safety = _clip(rng.normal(62 + 36 * reliability, 8, n), 40, 100)
    inspection = _clip(rng.normal(70 + 28 * reliability, 7, n), 45, 100)
    planned = rng.uniform(40, 95, n)
    actual = _clip(planned * (0.55 + 0.45 * reliability) + rng.normal(0, 5, n),
                   3, 100)
    schedule_slip = planned - actual
    delay_days = _clip(np.round((1 - reliability) * 22 + rng.normal(0, 3, n)),
                       0, 45)
    open_issues = _clip(np.round((1 - reliability) * 9 + rng.normal(0, 1.5, n)),
                        0, 16)
    contract_value = rng.uniform(200_000, 1_000_000, n)
    invoice = contract_value * rng.uniform(0.3, 0.9, n)
    paid = np.clip(
        invoice * (1 + (0.5 - reliability) * 0.35 + rng.normal(0, 0.05, n)),
        0, None)
    overrun_pct = np.where(invoice > 0, (paid - invoice) / invoice * 100, 0)
    engineer = _clip(2.4 + 2.6 * reliability + rng.normal(0, 0.3, n), 1, 5)
    client = _clip(2.4 + 2.6 * reliability + rng.normal(0, 0.3, n), 1, 5)

    # Current workload (for capacity-aware recommendation).
    capacity = np.clip(np.round(contract_value / 200_000) + 1, 2, 6)
    active = np.clip(capacity + rng.integers(-2, 3, n), 1, 12)
    utilization = active / capacity * 100

    # --- normalized KPIs (used only to build the hidden targets) ---
    quality_kpi = _clip(0.7 * quality + 0.3 * inspection)
    schedule_kpi = _clip(actual / planned * 100 - delay_days * 2)
    cost_kpi = _clip(100 - np.maximum(0, overrun_pct))
    safety_kpi = _clip(safety)
    client_kpi = _clip(client * 20)

    # --- hidden PERFORMANCE SCORE (non-linear: safety gate + interaction) ---
    perf = (0.30 * quality_kpi + 0.22 * schedule_kpi + 0.18 * cost_kpi
            + 0.15 * safety_kpi + 0.15 * client_kpi)
    perf -= np.where(safety_kpi < 60, (60 - safety_kpi) * 0.7, 0)      # gate
    perf += np.where((quality_kpi > 85) & (schedule_kpi > 85), 4, 0)   # synergy
    perf -= open_issues * 0.4
    perf = _clip(perf + rng.normal(0, 2.5, n))

    # --- hidden delay outcome -> 3 classes ---
    delay_logit = (-2.2 + 0.055 * schedule_slip + 0.10 * delay_days
                   + 0.14 * open_issues - 0.03 * (quality - 70)
                   + rng.normal(0, 0.6, n))
    delay_p = _sigmoid(delay_logit)
    delay_label = np.where(delay_p > 0.66, 2, np.where(delay_p > 0.33, 1, 0))

    # --- hidden contract-breach outcome -> 3 classes ---
    breach_logit = (-2.6 + 0.19 * open_issues + 0.045 * np.maximum(0, overrun_pct)
                    + 0.09 * delay_days - 0.035 * (quality - 70)
                    + rng.normal(0, 0.6, n))
    breach_p = _sigmoid(breach_logit)
    breach_label = np.where(breach_p > 0.6, 2, np.where(breach_p > 0.3, 1, 0))

    # --- hidden RECOMMENDATION (manager decision) -> 5 classes ---
    util = active / capacity
    reco = np.select(
        [
            (util > 1) & (perf >= 63) & (breach_label < 2),      # at capacity
            (perf >= 87) & (delay_label == 0) & (breach_label == 0),
            (perf >= 77) & (breach_label < 2),
            (perf >= 62),
        ],
        [4, 3, 2, 1],
        default=0,
    )
    # Manager inconsistency: flip ~8% of labels.
    flip = rng.random(n) < 0.08
    reco = reco.copy()
    reco[flip] = rng.integers(0, 5, int(flip.sum()))

    features = {
        "planned_progress": planned, "actual_progress": actual,
        "schedule_slip": schedule_slip, "quality_score": quality,
        "safety_score": safety, "inspection_pass": inspection,
        "delay_days": delay_days, "open_issues": open_issues,
        "contract_value": contract_value, "invoice_amount": invoice,
        "paid_amount": paid, "overrun_pct": overrun_pct,
        "engineer_rating": engineer, "client_rating": client,
        "utilization": utilization,
    }
    return {
        "features": features,
        "perf_score": perf,
        "delay_label": delay_label,
        "breach_label": breach_label,
        "reco_label": reco,
    }


# ---- Module 2: materials ------------------------------------------------------
def generate_materials(n: int = 2500, seed: int = 43) -> dict:
    rng = np.random.default_rng(seed)

    required = rng.uniform(200, 12_000, n)
    current = required * rng.uniform(0.05, 1.3, n)
    minimum = required * rng.uniform(0.10, 0.40, n)
    lead = rng.integers(2, 22, n).astype(float)
    unit_price = rng.uniform(0.5, 700, n)
    reliability = np.clip(rng.normal(90, 6, n), 68, 100)

    # Hidden demand driver: project-phase intensity (not a feature) + noise.
    phase = rng.uniform(0.8, 1.35, n)
    demand = np.clip(
        required * phase * (1 + (100 - reliability) / 100 * 0.30)
        + rng.normal(0, required * 0.03, n), 0, None)

    # Hidden delivery-delay outcome -> 3 classes.
    delay_logit = (-3.0 + 0.22 * lead - 0.11 * (reliability - 90)
                   + 0.00004 * required + rng.normal(0, 0.6, n))
    delay_p = _sigmoid(delay_logit)
    delay_label = np.where(delay_p > 0.6, 2, np.where(delay_p > 0.3, 1, 0))

    # Hidden OPTIMAL REORDER quantity (inventory optimization):
    # cover demand over the lead window + reliability-scaled safety stock.
    safety_stock = minimum * (1 + (100 - reliability) / 100 * 0.6)
    reorder = np.maximum(
        0, demand * (1 + lead / 60) + safety_stock - current
        + rng.normal(0, required * 0.02, n))

    features = {
        "current_stock": current, "minimum_stock": minimum,
        "required_qty": required, "lead_time_days": lead,
        "unit_price": unit_price, "delivery_reliability": reliability,
    }
    return {
        "features": features,
        "demand": demand,
        "delay_label": delay_label,
        "reorder": reorder,
    }


# ---- Suppliers (for supplier-performance scoring) -----------------------------
def generate_suppliers(n: int = 2500, seed: int = 44) -> dict:
    rng = np.random.default_rng(seed)

    reliability = np.clip(rng.normal(90, 6, n), 68, 100)
    lead = rng.integers(2, 22, n).astype(float)
    price_pct = rng.uniform(0, 1, n)  # within-category price percentile (0=cheap)

    lead_speed = _clip(100 - lead / 30 * 100)
    # Hidden supplier PERFORMANCE outcome (non-linear penalties).
    perf = 0.5 * reliability + 0.28 * lead_speed + 0.22 * (100 - price_pct * 100)
    perf -= np.where(lead > 16, (lead - 16) * 2.5, 0)           # long-lead penalty
    perf -= np.where(reliability < 80, (80 - reliability) * 1.2, 0)  # unreliable
    perf = _clip(perf + rng.normal(0, 3, n))

    features = {
        "delivery_reliability": reliability,
        "lead_time_days": lead,
        "price_percentile": price_pct,
    }
    return {"features": features, "perf": perf}
