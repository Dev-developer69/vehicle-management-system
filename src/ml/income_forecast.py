-"""
Income Forecast — src/ml/diesel_forecast.py jaisa hi simple, explainable
recency-weighted average pattern, income ke liye. Recent din jyada weight
paate hain (naya trend jaldi capture ho), aur usi weighted daily average
se agle N din ka total income forecast hota hai.
"""

import pandas as pd


def forecast_income(raw_rows: list, forecast_days: int = 15) -> dict:
    """raw_rows: list of {"bus_number", "date", "income", ...} dicts.
    Returns: {bus_number: {"forecast_income": float, "avg_daily_income": float,
                            "basis_days": int}} — sirf un buses ke liye jinke
    paas kam se kam 1 valid (income>0) record ho."""
    if not raw_rows:
        return {}
    df = pd.DataFrame(raw_rows)
    required = {"bus_number", "date", "income"}
    if df.empty or not required.issubset(df.columns):
        return {}

    df["income"] = pd.to_numeric(df["income"], errors="coerce")
    df["date"]   = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["income", "date"])
    df = df[df["income"] > 0]
    if df.empty:
        return {}

    results = {}
    for bus, g in df.groupby("bus_number"):
        g = g.sort_values("date")
        recent = g.tail(30)  # ✅ sirf recent 30 records ka window — bahut purana data trend ko na bigade
        n = len(recent)
        if n == 0:
            continue
        weights = pd.Series(range(1, n + 1), index=recent.index)  # linearly increasing — naye record ko zyada weight
        avg_daily = float((recent["income"] * weights).sum() / weights.sum())
        results[bus] = {
            "forecast_income": round(avg_daily * forecast_days, 0),
            "avg_daily_income": round(avg_daily, 2),
            "basis_days": n,
        }
    return results


def income_forecast_summary_rows(income_forecast: dict, diesel_forecast: dict = None, rate_per_litre: float = 95.69) -> list:
    """UI table ke liye rows — agar diesel_forecast (diesel_forecast.py se)
    diya jaaye, to estimated diesel cost aur estimated net bhi dikhata hai."""
    rows = []
    diesel_forecast = diesel_forecast or {}
    for bus, f in income_forecast.items():
        row = {
            "Bus": bus,
            "Avg Daily Income (₹)": f["avg_daily_income"],
            "Forecast Income (₹)": f["forecast_income"],
            "Basis (days)": f["basis_days"],
        }
        d = diesel_forecast.get(bus)
        if d:
            est_diesel_cost = round(d.get("forecast_litres", 0) * rate_per_litre, 0)
            row["Est. Diesel Cost (₹)"] = est_diesel_cost
            row["Est. Net (₹)"] = round(f["forecast_income"] - est_diesel_cost, 0)
        rows.append(row)
    rows.sort(key=lambda r: r["Forecast Income (₹)"], reverse=True)
    return rows
