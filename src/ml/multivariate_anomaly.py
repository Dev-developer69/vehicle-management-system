"""
Multivariate Anomaly Detection — Isolation Forest se ek saath kai signals
(mileage, income, actual KM) dekh kar anomaly pakadta hai.

Single-variable z-score (mileage_anomaly.py, income_anomaly.py) alag-alag
check karte hain. Ye module un sabko EK SAATH dekhta hai — jaise "kam
mileage + kam income + zyada diesel" ek saath ho to wo akele-akele
threshold cross na kare tab bhi combined pattern anomaly ho sakta hai.
"""

import pandas as pd

MIN_RECORDS_FOR_FOREST = 10   # itne records na ho to Isolation Forest reliable nahi
DEFAULT_CONTAMINATION  = 0.1  # expected anomaly fraction (~10%)


def detect_multivariate_anomalies(records: pd.DataFrame, contamination: float = DEFAULT_CONTAMINATION) -> pd.DataFrame:
    """records: columns me "bus_number", "km_per_litre", "income_per_km",
    "actual_km" hone chahiye. Har bus ke liye alag se Isolation Forest
    fit hota hai (taaki ek bus ka pattern doosre bus se compare na ho).
    Returns: same DataFrame + "is_anomaly" (bool) aur "anomaly_score" (float,
    jitna negative utna zyada anomalous) columns."""
    out = records.copy()
    out["is_anomaly"]    = False
    out["anomaly_score"] = 0.0

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return out

    feature_cols = ["km_per_litre", "income_per_km", "actual_km"]
    for col in feature_cols:
        if col not in out.columns:
            return out

    for bus, g in out.groupby("bus_number"):
        valid = g.dropna(subset=feature_cols)
        if len(valid) < MIN_RECORDS_FOR_FOREST:
            continue

        X = valid[feature_cols].values
        model = IsolationForest(
            contamination=contamination, random_state=42, n_estimators=100
        )
        preds  = model.fit_predict(X)          # -1 = anomaly, 1 = normal
        scores = model.decision_function(X)    # kam (negative) = zyada anomalous

        out.loc[valid.index, "is_anomaly"]    = preds == -1
        out.loc[valid.index, "anomaly_score"] = scores.round(3)

    return out
