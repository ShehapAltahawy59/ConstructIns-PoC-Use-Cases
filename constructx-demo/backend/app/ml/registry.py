"""Train, evaluate, persist and serve the ConstructX RandomForest models.

Eight scikit-learn models are trained on the synthetic datasets:

  Subcontractor module
    sub_score   RandomForestRegressor   — performance score (AI Score)
    sub_delay   RandomForestClassifier  — delay risk (3-class)
    sub_breach  RandomForestClassifier  — contract-breach risk (3-class)
    sub_reco    RandomForestClassifier  — vendor recommendation (5-class)

  Material module
    mat_demand  RandomForestRegressor   — material demand forecast
    mat_reorder RandomForestRegressor   — optimal reorder quantity
    mat_delay   RandomForestClassifier  — supplier delivery-delay risk (3-class)
    sup_score   RandomForestRegressor   — supplier performance score

Each is evaluated on a held-out test split (accuracy / macro-F1 for classifiers,
R² / MAE for regressors) and then refit on the full data for inference.
"""
from __future__ import annotations

import os
import threading

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score, f1_score, mean_absolute_error, r2_score,
)
from sklearn.model_selection import train_test_split

from . import datagen

MODELS_DIR = os.getenv("MODELS_DIR", "/code/models")

_STATE: dict = {}
_LOCK = threading.Lock()


def _top_importances(model, names, k=6):
    imp = getattr(model, "feature_importances_", None)
    if imp is None:
        return []
    order = np.argsort(imp)[::-1][:k]
    return [{"feature": names[i], "importance": round(float(imp[i]), 3)}
            for i in order]


def _train_classifier(X, y, names, label, classes):
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=7, stratify=y)
    clf = RandomForestClassifier(
        n_estimators=200, min_samples_leaf=2, random_state=42, n_jobs=-1)
    clf.fit(X_tr, y_tr)
    pred = clf.predict(X_te)
    metrics = {
        "algorithm": "RandomForestClassifier", "task": label,
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "accuracy": round(float(accuracy_score(y_te, pred)), 3),
        "macro_f1": round(float(f1_score(y_te, pred, average="macro")), 3),
        "classes": classes,
    }
    clf.fit(X, y)
    metrics["feature_importances"] = _top_importances(clf, names)
    return clf, metrics


def _train_regressor(X, y, names, label):
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=7)
    reg = RandomForestRegressor(
        n_estimators=250, min_samples_leaf=2, random_state=42, n_jobs=-1)
    reg.fit(X_tr, y_tr)
    pred = reg.predict(X_te)
    metrics = {
        "algorithm": "RandomForestRegressor", "task": label,
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "r2": round(float(r2_score(y_te, pred)), 3),
        "mae": round(float(mean_absolute_error(y_te, pred)), 1),
    }
    reg.fit(X, y)
    metrics["feature_importances"] = _top_importances(reg, names)
    return reg, metrics


def _build_and_train() -> dict:
    models, metrics, labels = {}, {}, {}

    # ---- subcontractor models
    sub = datagen.generate_subcontractors()
    Xs = datagen.assemble(sub["features"], datagen.SUB_FEATURES)
    Xr = datagen.assemble(sub["features"], datagen.SUB_RECO_FEATURES)

    models["sub_score"], metrics["sub_score"] = _train_regressor(
        Xs, sub["perf_score"], datagen.SUB_FEATURES, "Performance score")
    models["sub_delay"], metrics["sub_delay"] = _train_classifier(
        Xs, sub["delay_label"], datagen.SUB_FEATURES, "Delay risk",
        datagen.RISK_CLASSES)
    models["sub_breach"], metrics["sub_breach"] = _train_classifier(
        Xs, sub["breach_label"], datagen.SUB_FEATURES, "Contract-breach risk",
        datagen.RISK_CLASSES)
    models["sub_reco"], metrics["sub_reco"] = _train_classifier(
        Xr, sub["reco_label"], datagen.SUB_RECO_FEATURES, "Vendor recommendation",
        datagen.RECO_CLASSES)
    labels["sub_delay"] = datagen.RISK_CLASSES
    labels["sub_breach"] = datagen.RISK_CLASSES
    labels["sub_reco"] = datagen.RECO_CLASSES

    # ---- material models
    mat = datagen.generate_materials()
    Xd = datagen.assemble(mat["features"], datagen.MAT_DEMAND_FEATURES)
    Xl = datagen.assemble(mat["features"], datagen.MAT_DELAY_FEATURES)
    Xro = datagen.assemble(mat["features"], datagen.MAT_REORDER_FEATURES)

    models["mat_demand"], metrics["mat_demand"] = _train_regressor(
        Xd, mat["demand"], datagen.MAT_DEMAND_FEATURES, "Demand forecast")
    models["mat_reorder"], metrics["mat_reorder"] = _train_regressor(
        Xro, mat["reorder"], datagen.MAT_REORDER_FEATURES, "Optimal reorder qty")
    models["mat_delay"], metrics["mat_delay"] = _train_classifier(
        Xl, mat["delay_label"], datagen.MAT_DELAY_FEATURES,
        "Supplier delivery-delay risk", datagen.RISK_CLASSES)
    labels["mat_delay"] = datagen.RISK_CLASSES

    # ---- supplier performance model
    sup = datagen.generate_suppliers()
    Xsup = datagen.assemble(sup["features"], datagen.SUP_FEATURES)
    models["sup_score"], metrics["sup_score"] = _train_regressor(
        Xsup, sup["perf"], datagen.SUP_FEATURES, "Supplier performance score")

    return {"models": models, "metrics": metrics, "labels": labels}


def ensure_trained() -> None:
    """Idempotently load persisted models or train them once (thread-safe)."""
    if _STATE:
        return
    with _LOCK:
        if _STATE:
            return
        bundle_path = os.path.join(MODELS_DIR, "constructx_models.joblib")
        if os.path.exists(bundle_path):
            try:
                _STATE.update(joblib.load(bundle_path))
                print("[ml] loaded persisted models")
                return
            except Exception as exc:  # pragma: no cover
                print(f"[ml] failed to load models ({exc}); retraining")

        print("[ml] training 8 RandomForest models on synthetic datasets...")
        bundle = _build_and_train()
        _STATE.update(bundle)
        try:
            os.makedirs(MODELS_DIR, exist_ok=True)
            joblib.dump(bundle, bundle_path)
        except OSError:
            pass
        for key, m in bundle["metrics"].items():
            score = m.get("accuracy", m.get("r2"))
            unit = "acc" if "accuracy" in m else "R2"
            print(f"[ml]   {key}: {m['algorithm']} -> {unit}={score}")


# ---- inference helpers --------------------------------------------------------
def _predict_label(key: str, features: dict, names: list[str]) -> str:
    ensure_trained()
    X = datagen.assemble(features, names)
    idx = int(_STATE["models"][key].predict(X)[0])
    return _STATE["labels"][key][idx]


def _predict_value(key: str, features: dict, names: list[str]) -> float:
    ensure_trained()
    X = datagen.assemble(features, names)
    return float(_STATE["models"][key].predict(X)[0])


# ---- batch inference (fast path for the dashboard) ----------------------------
def _matrix(feats: list[dict], names: list[str]) -> np.ndarray:
    return np.array([[float(f[n]) for n in names] for f in feats], dtype=float)


def _labels_batch(key: str, feats: list[dict], names: list[str]) -> list[str]:
    ensure_trained()
    if not feats:
        return []
    preds = _STATE["models"][key].predict(_matrix(feats, names))
    lab = _STATE["labels"][key]
    return [lab[int(p)] for p in preds]


def _values_batch(key: str, feats: list[dict], names: list[str]) -> list[float]:
    ensure_trained()
    if not feats:
        return []
    return [float(v) for v in _STATE["models"][key].predict(_matrix(feats, names))]


def predict_sub_score_batch(feats):
    return [round(v, 1) for v in _values_batch("sub_score", feats, datagen.SUB_FEATURES)]


def predict_sub_delay_batch(feats):
    return _labels_batch("sub_delay", feats, datagen.SUB_FEATURES)


def predict_sub_breach_batch(feats):
    return _labels_batch("sub_breach", feats, datagen.SUB_FEATURES)


def predict_sub_reco_batch(feats):
    return _labels_batch("sub_reco", feats, datagen.SUB_RECO_FEATURES)


def predict_material_demand_batch(feats):
    return [int(round(v)) for v in
            _values_batch("mat_demand", feats, datagen.MAT_DEMAND_FEATURES)]


def predict_material_reorder_batch(feats):
    return [max(0, int(round(v))) for v in
            _values_batch("mat_reorder", feats, datagen.MAT_REORDER_FEATURES)]


def predict_material_delay_batch(feats):
    return _labels_batch("mat_delay", feats, datagen.MAT_DELAY_FEATURES)


def predict_supplier_score_batch(feats):
    return [round(v, 1) for v in
            _values_batch("sup_score", feats, datagen.SUP_FEATURES)]


# ---- public inference API -----------------------------------------------------
def predict_sub_score(features: dict) -> float:
    return round(_predict_value("sub_score", features, datagen.SUB_FEATURES), 1)


def predict_sub_delay(features: dict) -> str:
    return _predict_label("sub_delay", features, datagen.SUB_FEATURES)


def predict_sub_breach(features: dict) -> str:
    return _predict_label("sub_breach", features, datagen.SUB_FEATURES)


def predict_sub_reco(features: dict) -> str:
    return _predict_label("sub_reco", features, datagen.SUB_RECO_FEATURES)


def predict_material_demand(features: dict) -> int:
    return int(round(_predict_value("mat_demand", features,
                                    datagen.MAT_DEMAND_FEATURES)))


def predict_material_reorder(features: dict) -> int:
    return max(0, int(round(_predict_value("mat_reorder", features,
                                           datagen.MAT_REORDER_FEATURES))))


def predict_material_delay(features: dict) -> str:
    return _predict_label("mat_delay", features, datagen.MAT_DELAY_FEATURES)


def predict_supplier_score(features: dict) -> float:
    return round(_predict_value("sup_score", features, datagen.SUP_FEATURES), 1)


def model_info(keys: list[str] | None = None) -> dict:
    ensure_trained()
    metrics = _STATE["metrics"]
    if keys:
        return {k: metrics[k] for k in keys if k in metrics}
    return metrics
