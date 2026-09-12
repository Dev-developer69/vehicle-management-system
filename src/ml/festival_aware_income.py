"""
Festival-Aware Income — income_anomaly.py ka baseline festival days ko
normal days ke saath mix kar deta hai, jisse do problems hoti hain:
  1. Festival ka high income "normal" maan liya jaata hai, aur agle
     normal din ka income usi inflated baseline se compare hoke galat
     "⚠️ Check" flag ho jaata hai.
  2. Festival din khud kabhi flag nahi hota (spike expected hi hota hai),
     lekin agar KOI conductor festival pe bhi average se kam le aaya,
     wo miss ho jaata hai kyunki baseline already high hai.

Fix: normal-day aur festival-day baseline ALAG seekhte hain, taaki
comparison hamesha apni category ke against ho.
"""

import pandas as pd

from src.ml.festival_calendar import is_festival_window, FESTIVALS_2026

MIN_HISTORY_FOR_ML   = 5
RED_FLAG_Z_THRESHOLD = -2.5
CHECK_Z_THRESHOLD    = -1.5


def _prep(raw_rows: list, extra_cols=()):
    if not raw_rows:
        return pd.DataFrame()
    df = pd.DataFrame(raw_rows)
    required = {"bus_number", "income", "actual_km", "date"} | set(extra_cols)
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()
    df["income"]    = pd.to_numeric(df["income"], errors="coerce")
    df["actual_km"] = pd.to_numeric(df["actual_km"], errors="coerce")
    df["date"]      = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["income", "actual_km", "date"])
    df = df[df["actual_km"] > 0]
    if df.empty:
        return df
    df["income_per_km"] = df["income"] / df["actual_km"]
    df["is_festival"] = df["date"].dt.date.apply(lambda d: is_festival_window(d)[0])
    return df


def compute_income_baseline_festival_aware(raw_rows: list) -> dict:
    """raw_rows: list of {"bus_number", "date", "income", "actual_km"} dicts.
    Returns: {bus_number: {"normal": {...}, "festival": {...}}} — dono keys
    mein {"mean", "std", "count"}, income_anomaly.py ke baseline dict jaisa
    hi shape, taaki existing UI code reuse ho sake."""
    df = _prep(raw_rows)
    if df.empty:
        return {}

    baseline = {}
    for bus, g in df.groupby("bus_number"):
        entry = {}
        for label, sub in (("normal", g[~g["is_festival"]]), ("festival", g[g["is_festival"]])):
            vals = sub["income_per_km"].dropna()
            if vals.empty:
                entry[label] = {"mean": None, "std": None, "count": 0}
            else:
                entry[label] = {
                    "mean":  float(vals.mean()),
                    "std":   float(vals.std(ddof=0) or 0.0),
                    "count": int(len(vals)),
                }
        baseline[bus] = entry
    return baseline


def income_alert_status_festival_aware(bus_number: str, record_date, actual_km, income_per_km, baseline: dict) -> str:
    """"🚨 Red flag" | "⚠️ Check" | "✅ Normal" | "🎉 Festival day" | "—"
    'record_date' ke hisaab se sahi baseline (normal/festival) choose karta hai."""
    if not actual_km or actual_km <= 0:
        return "—"
    if income_per_km is None or pd.isna(income_per_km):
        return "—"

    is_fest, fest_name, _ = is_festival_window(record_date)
    category = "festival" if is_fest else "normal"

    base_entry = baseline.get(bus_number, {}).get(category)
    if base_entry and base_entry["count"] >= MIN_HISTORY_FOR_ML and (base_entry["std"] or 0) > 0:
        z = (income_per_km - base_entry["mean"]) / base_entry["std"]
        if z <= RED_FLAG_Z_THRESHOLD:
            return f"🚨 Red flag ({fest_name})" if is_fest else "🚨 Red flag"
        if z <= CHECK_Z_THRESHOLD:
            return f"⚠️ Check ({fest_name})" if is_fest else "⚠️ Check"
        return f"🎉 {fest_name} — Normal" if is_fest else "✅ Normal"

    # Kaafi festival-day history nahi hai abhi — ML applicable nahi
    return f"🎉 {fest_name} — seekh raha hai" if is_fest else "✅ Normal"


def estimate_festival_income_multiplier(raw_rows: list) -> dict:
    """Har bus ke liye seekhta hai ki festival days pe normal days ke
    mukable income kitna guna (multiplier) hota hai — historical data se.
    Isse income_forecast.py ke forecast ko adjust kiya ja sakta hai jab
    forecast window mein koi known festival aata ho.
    Returns: {bus_number: {"multiplier": float, "basis_records": int}}"""
    df = _prep(raw_rows)
    if df.empty:
        return {}

    results = {}
    for bus, g in df.groupby("bus_number"):
        normal_avg   = g.loc[~g["is_festival"], "income_per_km"].mean()
        festival_avg = g.loc[g["is_festival"], "income_per_km"].mean()
        festival_n   = int(g["is_festival"].sum())
        if pd.isna(normal_avg) or normal_avg <= 0 or pd.isna(festival_avg) or festival_n < 2:
            results[bus] = {"multiplier": 1.3, "basis_records": festival_n}  # default assumption tak data na ho
            continue
        results[bus] = {
            "multiplier": round(float(festival_avg / normal_avg), 2),
            "basis_records": festival_n,
        }
    return results


def conductor_festival_performance(raw_rows: list) -> list:
    """raw_rows: list of {"conductor", "date", "income", "actual_km"} dicts.
    Sirf festival-window records par conductor-wise income/km rank karta
    hai — 'festival rush ko sabse achhe se kaun cash karta hai' dikhane
    ke liye (regular leaderboard se alag signal, kyunki kuch conductor
    normal din slow hote hain lekin bheed sambhalne mein best hote hain)."""
    if not raw_rows:
        return []
    df = pd.DataFrame(raw_rows)
    required = {"conductor", "date", "income", "actual_km"}
    if df.empty or not required.issubset(df.columns):
        return []

    df["income"]    = pd.to_numeric(df["income"], errors="coerce")
    df["actual_km"] = pd.to_numeric(df["actual_km"], errors="coerce")
    df["date"]      = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["income", "actual_km", "date"])
    df = df[df["actual_km"] > 0]
    df["is_festival"] = df["date"].dt.date.apply(lambda d: is_festival_window(d)[0])
    fest_df = df[df["is_festival"]]
    if fest_df.empty:
        return []

    rows = []
    for conductor, g in fest_df.groupby("conductor"):
        total_income = g["income"].sum()
        total_km = g["actual_km"].sum()
        rows.append({
            "Conductor": conductor,
            "Festival Income/KM (₹)": round(total_income / total_km, 2) if total_km else 0,
            "Festival Records": len(g),
        })
    rows.sort(key=lambda r: r["Festival Income/KM (₹)"], reverse=True)
    return rows
