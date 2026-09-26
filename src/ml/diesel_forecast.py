"""
Diesel Forecasting & Mileage Estimation.

This module has TWO independent pieces of logic that answer different
questions — keep both, don't merge them:

1. forecast_diesel() / forecast_summary_rows()
   "How much diesel (litres) will the next N days likely need?"
   — a simple day-by-day trend (linear regression) over daily diesel
   quantities. Used by src/screens/vehicle_records.py.

2. estimate_bus_mileage() / expected_diesel_cost() / compute_intervals()
   "What is the bus's real current mileage (km/L), and what will the
   NEXT PERIOD cost given its expected KM?"
   — reconstructs actual fill-to-fill interval KM from the daily
   'Actual KM' field (since the manual 'Diesel KM' field isn't reliably
   filled), then computes an outlier-robust, KM-weighted average mileage.
   Used by src/screens/bus_report_view.py.

Both are numpy/pandas-only — no heavy ML dependency.
"""

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════
# 1. DAY-TREND DIESEL-QUANTITY FORECAST
# ══════════════════════════════════════════════

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


# ══════════════════════════════════════════════
# 2. ACTUAL-KM-INTERVAL BASED MILEAGE ESTIMATION
# ══════════════════════════════════════════════
#
# 'Diesel KM' field manual entry pe depend karta hai jo reliably nahi bharta
# (pichle fill ke baad se kitna km chala, ye pata nahi rehta). Isliye yahan
# DAILY 'Actual KM' (jo already bharni padti hai — Vehicle Records ka core
# field) se interval-km khud reconstruct karte hain:
#
#   Har fuel-fill ka interval-km = us fill se PICHLE fill ke beech ke
#   saare din ka actual_km ka sum (fill-date included, prev fill-date
#   excluded).
#
# Real-world noise (traffic/idling/AC, ya galti se galat entry/meter-error)
# ki wajah se ek fill ka mileage kabhi upar-neeche ho sakta hai — isliye
# IQR-capping se ek outlier fill poore average ko nahi bigaadta.

MIN_KM_FOR_ESTIMATE = 500   # itna total interval-KM na ho to mileage estimate abhi unreliable hai
TREND_BUCKETS        = 4    # trend dekhne ke liye data ko itne chunks mein baanta hai

# ── Physical sanity bounds — kisi bhi bus ka mileage in ke bahar
# NAHI ho sakta (real-world diesel/CNG bus ranges). Ye do purpose serve
# karte hain:
# 1. HARD_BOUNDS: individual fill-intervals jo in bounds se bahar hain
#    (jaise 61 km/L) sirf data-entry/meter-error ho sakte hain — inhe
#    average nikalne se PEHLE hi drop kar dete hain, taaki wo IQR ko bhi
#    corrupt na kar sakein.
# 2. TYPICAL_RANGE: final average agar (real fills hone ke baad bhi) is
#    range se bahar aaye, to nearest bound par clamp kar dete hain aur
#    "range_capped" flag True kar dete hain — taaki UI chahe to warna
#    dikha sake.
HARD_BOUNDS   = {"diesel": (1.0, 10.0), "cng": (1.5, 12.0)}   # generous — sirf impossible values drop karne ke liye
TYPICAL_RANGE = {"diesel": (3.0, 6.0),  "cng": (4.0, 7.0)}     # realistic range — isse bahar aaye to clamp + flag


def compute_intervals(vr_df: pd.DataFrame, fills_df: pd.DataFrame) -> pd.DataFrame:
    """vr_df: Vehicle Records ki FULL history — columns 'Date', 'Actual KM'
    (Status == 'On Leave' wale din already 0 KM hote hain, wo apne aap
    correctly count ho jaate hain).
    fills_df: get_all_fuel_fills() se — columns 'Date', 'Quantity'.
    Returns: DataFrame [interval_start, interval_end, km_in_interval,
                        diesel_filled, mileage] — ek row per fill (pehle
    fill ko chhodke, kyunki uske paas pichla reference nahi hai)."""
    if vr_df.empty or fills_df.empty:
        return pd.DataFrame(columns=["interval_start", "interval_end", "km_in_interval", "diesel_filled", "mileage"])

    vr = vr_df.copy()
    vr["Date"] = pd.to_datetime(vr["Date"])
    vr["Actual KM"] = pd.to_numeric(vr["Actual KM"], errors="coerce").fillna(0)
    vr = vr.sort_values("Date")

    # ── Same date pe multiple fills ho sakte hain — pehle date-wise sum karo ──
    f = fills_df.copy()
    f["Date"] = pd.to_datetime(f["Date"])
    f["Quantity"] = pd.to_numeric(f["Quantity"], errors="coerce").fillna(0)
    fill_totals = f.groupby("Date")["Quantity"].sum().reset_index().sort_values("Date")
    fill_totals = fill_totals[fill_totals["Quantity"] > 0]

    if len(fill_totals) < 2:
        return pd.DataFrame(columns=["interval_start", "interval_end", "km_in_interval", "diesel_filled", "mileage"])

    rows = []
    prev_date = fill_totals.iloc[0]["Date"]
    for _, frow in fill_totals.iloc[1:].iterrows():
        curr_date = frow["Date"]
        mask = (vr["Date"] > prev_date) & (vr["Date"] <= curr_date)
        km_in_interval = vr.loc[mask, "Actual KM"].sum()
        diesel_filled  = float(frow["Quantity"])
        if km_in_interval > 0 and diesel_filled > 0:
            rows.append({
                "interval_start": prev_date, "interval_end": curr_date,
                "km_in_interval": km_in_interval, "diesel_filled": diesel_filled,
                "mileage": km_in_interval / diesel_filled,
            })
        prev_date = curr_date
    return pd.DataFrame(rows)


def _robust_weighted_mileage(mileages: np.ndarray, weights: np.ndarray) -> float:
    """IQR-capping (outlier intervals exclude) + KM-weighted average (bada
    interval ka mileage zyada trust hota hai). Yeh HARD_BOUNDS-filtered
    intervals par chalta hai (impossible values already nikal chuke hain)."""
    if len(mileages) == 0:
        return 0.0
    if len(mileages) < 4:
        return float(np.average(mileages, weights=weights))
    q1, q3 = np.percentile(mileages, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mask = (mileages >= lo) & (mileages <= hi)
    if not mask.any():
        mask = np.ones_like(mileages, dtype=bool)  # sab outlier nikle to original hi use karo
    return float(np.average(mileages[mask], weights=weights[mask]))


def estimate_bus_mileage(vr_df: pd.DataFrame, fills_df: pd.DataFrame, fuel_type: str = "diesel") -> dict:
    """Ek bus ke liye robust, KM-weighted average mileage nikalta hai.
    `fuel_type`: "diesel" ya "cng" — physical sanity bounds isi se decide
    hote hain (diesel 1-10 km/L hard bound / 3-6 typical; CNG 1.5-12 /
    4-7 typical).
    Returns: {"avg_kmpl", "total_km", "total_diesel", "intervals_used",
              "intervals_dropped", "trend", "range_capped"}"""
    lo_hard, hi_hard = HARD_BOUNDS.get(fuel_type, HARD_BOUNDS["diesel"])
    lo_typ, hi_typ   = TYPICAL_RANGE.get(fuel_type, TYPICAL_RANGE["diesel"])

    intervals = compute_intervals(vr_df, fills_df)
    if intervals.empty:
        return {"avg_kmpl": 0.0, "total_km": 0.0, "total_diesel": 0.0,
                "intervals_used": 0, "intervals_dropped": 0,
                "trend": "abhi seekh raha hai", "range_capped": False}

    # ── Step 1: physically-impossible fill-intervals drop karo (meter-error,
    # galti se double/half entry) — ye average nikalne se PEHLE hi hatate
    # hain, taaki IQR bhi corrupt na ho ──
    n_before = len(intervals)
    valid = intervals[(intervals["mileage"] >= lo_hard) & (intervals["mileage"] <= hi_hard)]
    intervals_dropped = n_before - len(valid)
    if valid.empty:
        valid = intervals  # sab hi impossible nikle to original hi use karo (better than nothing)
        intervals_dropped = 0

    total_km, total_diesel = valid["km_in_interval"].sum(), valid["diesel_filled"].sum()

    if total_km < MIN_KM_FOR_ESTIMATE:
        return {
            "avg_kmpl": round(total_km / total_diesel, 2) if total_diesel else 0.0,
            "total_km": round(total_km, 0), "total_diesel": round(total_diesel, 1),
            "intervals_used": len(valid), "intervals_dropped": intervals_dropped,
            "trend": "abhi seekh raha hai", "range_capped": False,
        }

    avg_kmpl = _robust_weighted_mileage(valid["mileage"].values, valid["km_in_interval"].values)

    # ── Step 2: final average bhi agar typical range se bahar aaye, to
    # nearest bound par clamp karo aur flag lagao — is card ne kabhi
    # 61 km/L jaisa impossible number nahi dikhana chahiye ──
    range_capped = False
    if avg_kmpl > 0 and not (lo_typ <= avg_kmpl <= hi_typ):
        avg_kmpl = min(max(avg_kmpl, lo_typ), hi_typ)
        range_capped = True

    # ── Trend: data ko chunks mein baant kar pehle vs aakhri chunk ka
    # KM-weighted mileage compare karo ──
    intervals_sorted = valid.sort_values("interval_end").reset_index(drop=True)
    n_buckets  = min(TREND_BUCKETS, len(intervals_sorted))
    chunk_size = max(1, len(intervals_sorted) // n_buckets)
    bucket_vals = []
    for i in range(0, len(intervals_sorted), chunk_size):
        chunk = intervals_sorted.iloc[i:i + chunk_size]
        if chunk["diesel_filled"].sum() > 0:
            bucket_vals.append(chunk["km_in_interval"].sum() / chunk["diesel_filled"].sum())

    if len(bucket_vals) >= 2 and bucket_vals[0] > 0:
        if bucket_vals[-1] > bucket_vals[0] * 1.05:
            trend = "📈 Mileage improve ho raha hai"
        elif bucket_vals[-1] < bucket_vals[0] * 0.95:
            trend = "📉 Mileage girr raha hai"
        else:
            trend = "➡️ Stable"
    else:
        trend = "➡️ Stable"

    return {
        "avg_kmpl": round(avg_kmpl, 2), "total_km": round(total_km, 0),
        "total_diesel": round(total_diesel, 1), "intervals_used": len(valid),
        "intervals_dropped": intervals_dropped, "trend": trend, "range_capped": range_capped,
    }


def expected_diesel_cost(estimate: dict, period_expected_km: float,
                          rate_per_litre: float, fallback_kmpl: float = None,
                          fuel_type: str = "diesel") -> dict:
    """Data-driven avg_kmpl ko period ke expected KM ke saath combine karke
    Expected Diesel Cost deta hai. Agar bus ke paas abhi kaafi data nahi hai
    (avg_kmpl 0), to `fallback_kmpl` (agar diya gaya) ya fuel_type ke
    TYPICAL_RANGE ka midpoint use hota hai."""
    if fallback_kmpl is None:
        lo, hi = TYPICAL_RANGE.get(fuel_type, TYPICAL_RANGE["diesel"])
        fallback_kmpl = round((lo + hi) / 2, 2)

    avg_kmpl = estimate.get("avg_kmpl") or 0.0
    used_fallback = avg_kmpl <= 0
    if used_fallback:
        avg_kmpl = fallback_kmpl

    expected_litres = period_expected_km / avg_kmpl if avg_kmpl > 0 else 0.0
    return {
        "expected_litres": round(expected_litres, 1),
        "expected_cost": round(expected_litres * rate_per_litre, 0),
        "avg_kmpl": round(avg_kmpl, 2),
        "used_fallback": used_fallback,
        "intervals_used": estimate.get("intervals_used", 0),
        "intervals_dropped": estimate.get("intervals_dropped", 0),
        "trend": estimate.get("trend", ""),
        "range_capped": estimate.get("range_capped", False),
    }
