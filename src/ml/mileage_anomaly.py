"""
Mileage Anomaly Detection — per-bus statistical (z-score) baseline model.

Poore app ka ML logic yahi ek jagah rehta hai. Baaki files (db.py,
vehicle_records.py) sirf isko call karte hain — data-fetch, computation,
aur UI teeno alag-alag layers me hain.

Kaam kaise karta hai:
- Har bus ka apna historical mileage (km/L) distribution seekha jaata hai
  (mean + standard deviation), poore available diesel-record history se.
- Naya record us bus ke apne learned baseline ke against z-score se
  compare hota hai — matlab fixed threshold nahi, har bus apna normal
  khud define karta hai.
- Jab tak kisi bus ke paas kaafi history na ho (MIN_HISTORY_FOR_ML se
  kam), tab tak ek simple fallback reference (FALLBACK_MIN_MILEAGE) use
  hota hai.
"""

import pandas as pd

FALLBACK_MIN_MILEAGE = 4.8   # bus ke paas kaafi history na ho tab tak yehi starting reference use hoga
MIN_HISTORY_FOR_ML   = 5     # itne diesel-records ke baad har bus apna khud ka baseline seekh leta hai

RED_FLAG_Z_THRESHOLD = -2.5  # isse neeche => extreme anomaly
CHECK_Z_THRESHOLD    = -1.5  # isse neeche => mild anomaly


def compute_mileage_baseline(raw_rows: list) -> dict:
    """raw_rows: list of {"bus_number", "diesel", "diesel_km"} dicts (jaise
    db.get_diesel_records_raw() se aata hai). Har bus ka mean/std/count
    seekh kar return karta hai.
    Returns: {bus_number: {"mean": float, "std": float, "count": int}}"""
    if not raw_rows:
        return {}

    bdf = pd.DataFrame(raw_rows)
    if bdf.empty or "diesel" not in bdf.columns or "diesel_km" not in bdf.columns:
        return {}

    bdf["diesel"]    = pd.to_numeric(bdf["diesel"], errors="coerce")
    bdf["diesel_km"] = pd.to_numeric(bdf["diesel_km"], errors="coerce")
    bdf = bdf.dropna(subset=["diesel", "diesel_km"])
    bdf = bdf[bdf["diesel"] > 0]
    if bdf.empty:
        return {}
    bdf["km_per_litre"] = bdf["diesel_km"] / bdf["diesel"]

    baseline = {}
    for bus, g in bdf.groupby("bus_number"):
        vals = g["km_per_litre"].dropna()
        if vals.empty:
            continue
        baseline[bus] = {
            "mean":  float(vals.mean()),
            "std":   float(vals.std(ddof=0) or 0.0),
            "count": int(len(vals)),
        }
    return baseline


def mileage_zscore(bus_number: str, km_per_litre, baseline: dict):
    """Bus ke apne baseline ke against z-score deta hai. Agar bus ke paas
    kaafi history nahi hai to None deta hai (ML abhi applicable nahi)."""
    if km_per_litre is None or pd.isna(km_per_litre):
        return None
    base = baseline.get(bus_number)
    if not base or base["count"] < MIN_HISTORY_FOR_ML or base["std"] <= 0:
        return None
    return round((km_per_litre - base["mean"]) / base["std"], 2)


def mileage_alert_status(bus_number: str, actual_km, diesel, km_per_litre, baseline: dict) -> str:
    """Ek record ke liye alert status deta hai:
    "🚨 Red flag" | "⚠️ Check" | "✅ Normal" | "—" """
    if diesel and diesel > 0 and (actual_km or 0) == 0:
        return "🚨 Red flag"

    if km_per_litre is not None and not pd.isna(km_per_litre):
        base = baseline.get(bus_number)
        if base and base["count"] >= MIN_HISTORY_FOR_ML and base["std"] > 0:
            z = (km_per_litre - base["mean"]) / base["std"]
            if z <= RED_FLAG_Z_THRESHOLD:
                return "🚨 Red flag"
            if z <= CHECK_Z_THRESHOLD:
                return "⚠️ Check"
        elif km_per_litre < FALLBACK_MIN_MILEAGE:
            # Naye bus ke paas abhi kaafi history nahi — fallback reference use karo
            return "⚠️ Check"

    if diesel and diesel > 0:
        return "✅ Normal"
    return "—"


def baseline_summary_rows(baseline: dict) -> list:
    """UI me dikhane ke liye har bus ka baseline ek readable row-list me deta hai."""
    rows = []
    for bus in sorted(baseline.keys()):
        b = baseline[bus]
        learned = b["count"] >= MIN_HISTORY_FOR_ML
        rows.append({
            "Bus": bus,
            "Avg Mileage (km/L)": round(b["mean"], 2),
            "Std Dev": round(b["std"], 2),
            "Diesel Records": b["count"],
            "Status": (
                "✅ ML baseline active" if learned
                else f"⏳ Fallback ({FALLBACK_MIN_MILEAGE} km/L) — {MIN_HISTORY_FOR_ML - b['count']} aur records chahiye"
            ),
        })
    return rows
