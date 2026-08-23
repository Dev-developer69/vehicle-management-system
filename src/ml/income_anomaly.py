"""
Income Anomaly Detection — per-bus statistical (z-score) baseline model,
mileage_anomaly.py jaisa hi pattern lekin Income per KM ke liye.

Kaam: har bus ka apna historical "income per km" seekh leta hai (mean +
std deviation), aur naye din ka income us baseline ke against compare
karta hai. Agar kisi din ka income achanak bahut kam ho (revenue
leakage/fraud/data-entry-miss ka signal ho sakta hai), to flag hota hai.
"""

import pandas as pd

MIN_HISTORY_FOR_ML = 5     # itne records ke baad har bus apna baseline seekh leta hai
RED_FLAG_Z_THRESHOLD = -2.5
CHECK_Z_THRESHOLD    = -1.5


def compute_income_baseline(raw_rows: list) -> dict:
    """raw_rows: list of {"bus_number", "income", "actual_km"} dicts.
    Returns: {bus_number: {"mean": float, "std": float, "count": int}}"""
    if not raw_rows:
        return {}

    idf = pd.DataFrame(raw_rows)
    if idf.empty or "income" not in idf.columns or "actual_km" not in idf.columns:
        return {}

    idf["income"]    = pd.to_numeric(idf["income"], errors="coerce")
    idf["actual_km"] = pd.to_numeric(idf["actual_km"], errors="coerce")
    idf = idf.dropna(subset=["income", "actual_km"])
    idf = idf[idf["actual_km"] > 0]
    if idf.empty:
        return {}
    idf["income_per_km"] = idf["income"] / idf["actual_km"]

    baseline = {}
    for bus, g in idf.groupby("bus_number"):
        vals = g["income_per_km"].dropna()
        if vals.empty:
            continue
        baseline[bus] = {
            "mean":  float(vals.mean()),
            "std":   float(vals.std(ddof=0) or 0.0),
            "count": int(len(vals)),
        }
    return baseline


def income_zscore(bus_number: str, income_per_km, baseline: dict):
    if income_per_km is None or pd.isna(income_per_km):
        return None
    base = baseline.get(bus_number)
    if not base or base["count"] < MIN_HISTORY_FOR_ML or base["std"] <= 0:
        return None
    return round((income_per_km - base["mean"]) / base["std"], 2)


def income_alert_status(bus_number: str, actual_km, income_per_km, baseline: dict) -> str:
    """"🚨 Red flag" | "⚠️ Check" | "✅ Normal" | "—" """
    if not actual_km or actual_km <= 0:
        return "—"
    if income_per_km is None or pd.isna(income_per_km):
        return "—"

    base = baseline.get(bus_number)
    if base and base["count"] >= MIN_HISTORY_FOR_ML and base["std"] > 0:
        z = (income_per_km - base["mean"]) / base["std"]
        if z <= RED_FLAG_Z_THRESHOLD:
            return "🚨 Red flag"
        if z <= CHECK_Z_THRESHOLD:
            return "⚠️ Check"
        return "✅ Normal"

    # Kaafi history nahi — abhi ML applicable nahi, sirf "Normal" maano
    return "✅ Normal"


def income_baseline_summary_rows(baseline: dict) -> list:
    rows = []
    for bus in sorted(baseline.keys()):
        b = baseline[bus]
        learned = b["count"] >= MIN_HISTORY_FOR_ML
        rows.append({
            "Bus": bus,
            "Avg Income/KM (₹)": round(b["mean"], 2),
            "Std Dev": round(b["std"], 2),
            "Records": b["count"],
            "Status": "✅ ML baseline active" if learned else f"⏳ Seekh raha hai — {MIN_HISTORY_FOR_ML - b['count']} aur records chahiye",
        })
    return rows
