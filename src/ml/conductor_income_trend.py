"""
Conductor Income Trend — driver_income_trend.py jaisa hi pattern, lekin
CONDUCTOR ke liye. Real-world mein income aana/na-aana mostly conductor
pe depend karta hai (wahi fare collect karta hai), driver sirf gaadi
chalata hai — isliye conductor ka apna trend track karna zyada
actionable hai driver ke trend se.

Har conductor ko UNKE APNE past se compare karta hai (cross-sectional
"best conductor" leaderboard jaisa nahi) — taaki "ye conductor is mahine
slip ho raha hai" jaisa early-warning signal mile.
"""

import numpy as np
import pandas as pd

MIN_RECORDS_FOR_TREND = 5     # itne records na ho to trend detect karna unreliable hai
SIGNIFICANT_SLOPE_PCT = 0.03  # avg income/km ka 3%+ per-record slope => significant trend


def compute_conductor_income_trends(raw_rows: list) -> dict:
    """raw_rows: list of {"conductor", "date", "income", "actual_km"} dicts.
    Returns: {conductor: {"avg_income_per_km": float, "slope": float,
                           "trend": str, "records": int}}"""
    if not raw_rows:
        return {}

    cdf = pd.DataFrame(raw_rows)
    required = {"conductor", "date", "income", "actual_km"}
    if cdf.empty or not required.issubset(cdf.columns):
        return {}

    cdf["income"]    = pd.to_numeric(cdf["income"], errors="coerce")
    cdf["actual_km"] = pd.to_numeric(cdf["actual_km"], errors="coerce")
    cdf["date"]      = pd.to_datetime(cdf["date"], errors="coerce")
    cdf = cdf.dropna(subset=["income", "actual_km", "date"])
    cdf = cdf[cdf["actual_km"] > 0]
    if cdf.empty:
        return {}
    cdf["income_per_km"] = cdf["income"] / cdf["actual_km"]

    results = {}
    for conductor, g in cdf.groupby("conductor"):
        g = g.sort_values("date")
        vals = g["income_per_km"].values
        if len(vals) < MIN_RECORDS_FOR_TREND:
            results[conductor] = {
                "avg_income_per_km": round(float(vals.mean()), 2),
                "slope": None,
                "trend": "abhi seekh raha hai",
                "records": len(vals),
            }
            continue

        x = np.arange(len(vals))
        slope, intercept = np.polyfit(x, vals, 1)
        avg = float(vals.mean())

        if slope > avg * SIGNIFICANT_SLOPE_PCT:
            trend_label = "📈 Improving"
        elif slope < -avg * SIGNIFICANT_SLOPE_PCT:
            trend_label = "📉 Declining"
        else:
            trend_label = "➡️ Stable"

        results[conductor] = {
            "avg_income_per_km": round(avg, 2),
            "slope": round(float(slope), 3),
            "trend": trend_label,
            "records": len(vals),
        }
    return results


def conductor_income_trend_rows(trends: dict) -> list:
    """UI ke liye rows — 'Declining' conductors ko upar sort karta hai
    taaki attention sabse pehle unhi pe jaaye (income-loss ka sabse bada
    reason yahi log hote hain)."""
    priority = {"📉 Declining": 0, "➡️ Stable": 1, "📈 Improving": 2, "abhi seekh raha hai": 3}
    rows = []
    for conductor, t in trends.items():
        rows.append({
            "Conductor": conductor,
            "Avg Income/KM (₹)": t["avg_income_per_km"],
            "Trend": t["trend"],
            "Records": t["records"],
        })
    rows.sort(key=lambda r: priority.get(r["Trend"], 4))
    return rows
