"""
Diesel Consumption Forecasting — har bus ka agla period ka expected diesel
consumption aur cost forecast karta hai, historical daily data ke trend se
(simple linear regression, koi heavy dependency nahi — sirf numpy).
"""

import numpy as np
import pandas as pd

MIN_DAYS_FOR_FORECAST = 5  # itne diesel-days na ho to forecast unreliable hai


def forecast_diesel(raw_rows: list, forecast_days: int = 15) -> dict:
    """raw_rows: list of {"bus_number", "date", "diesel"} dicts, diesel > 0 wale.
    Har bus ke liye agle `forecast_days` din ka expected total diesel (litres)
    forecast karta hai — linear trend (slope) + average ka combination.
    Returns: {bus_number: {"forecast_litres": float, "avg_daily": float,
                            "trend": "badh raha" | "ghat raha" | "stable",
                            "days_used": int}}"""
    if not raw_rows:
        return {}

    ddf = pd.DataFrame(raw_rows)
    if ddf.empty or "diesel" not in ddf.columns or "date" not in ddf.columns:
        return {}

    ddf["diesel"] = pd.to_numeric(ddf["diesel"], errors="coerce")
    ddf["date"]   = pd.to_datetime(ddf["date"], errors="coerce")
    ddf = ddf.dropna(subset=["diesel", "date"])
    ddf = ddf[ddf["diesel"] > 0]
    if ddf.empty:
        return {}

    results = {}
    for bus, g in ddf.groupby("bus_number"):
        g = g.sort_values("date")
        if len(g) < MIN_DAYS_FOR_FORECAST:
            avg_daily = float(g["diesel"].mean())
            results[bus] = {
                "forecast_litres": round(avg_daily * forecast_days, 1),
                "avg_daily": round(avg_daily, 2),
                "trend": "abhi seekh raha hai",
                "days_used": len(g),
            }
            continue

        x = np.arange(len(g))
        y = g["diesel"].values
        slope, intercept = np.polyfit(x, y, 1)

        avg_daily = float(y.mean())
        # Trend-adjusted forecast: average + thoda sa slope-based adjustment,
        # taaki ek outlier din pura forecast na bigaad de
        trend_adjustment = slope * forecast_days * 0.5
        forecast_total = max(0.0, avg_daily * forecast_days + trend_adjustment)

        if slope > avg_daily * 0.02:
            trend_label = "📈 Badh raha hai"
        elif slope < -avg_daily * 0.02:
            trend_label = "📉 Ghat raha hai"
        else:
            trend_label = "➡️ Stable"

        results[bus] = {
            "forecast_litres": round(forecast_total, 1),
            "avg_daily": round(avg_daily, 2),
            "trend": trend_label,
            "days_used": len(g),
        }
    return results


def forecast_summary_rows(forecast: dict, rate_per_litre: float = None) -> list:
    rows = []
    for bus in sorted(forecast.keys()):
        f = forecast[bus]
        row = {
            "Bus": bus,
            "Avg Daily (L)": f["avg_daily"],
            "Trend": f["trend"],
            "Forecast (L)": f["forecast_litres"],
            "Based on (days)": f["days_used"],
        }
        if rate_per_litre:
            row["Est. Cost (₹)"] = round(f["forecast_litres"] * rate_per_litre, 0)
        rows.append(row)
    return rows
