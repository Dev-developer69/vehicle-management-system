"""
Diesel Mileage & Cost Estimation — actual_km-interval based, outlier-robust.

'Diesel KM' field manual entry pe depend karta hai jo reliably nahi bharta
(pichle fill ke baad se kitna km chala, ye pata nahi rehta). Isliye yahan
DAILY 'Actual KM' (jo already bharni padti hai — Vehicle Records ka core
field) se interval-km khud reconstruct karte hain:

  Har fuel-fill ka interval-km = us fill se PICHLE fill ke beech ke
  saare din ka actual_km ka sum (fill-date included, prev fill-date
  excluded).

Ye poore tarah automatic hai — koi extra manual field ki zaroorat nahi.

Real-world noise (traffic/idling/AC, ya galti se galat entry/meter-error)
ki wajah se ek fill ka mileage kabhi upar-neeche ho sakta hai — isliye
IQR-capping se ek outlier fill poore average ko nahi bigaadta.
"""

import numpy as np
import pandas as pd

MIN_KM_FOR_ESTIMATE = 500   # itna total interval-KM na ho to mileage estimate abhi unreliable hai
TREND_BUCKETS        = 4    # trend dekhne ke liye data ko itne chunks mein baanta hai


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
    interval ka mileage zyada trust hota hai)."""
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


def estimate_bus_mileage(vr_df: pd.DataFrame, fills_df: pd.DataFrame) -> dict:
    """Ek bus ke liye robust, KM-weighted average mileage nikalta hai.
    Returns: {"avg_kmpl", "total_km", "total_diesel", "intervals_used", "trend"}"""
    intervals = compute_intervals(vr_df, fills_df)
    if intervals.empty:
        return {"avg_kmpl": 0.0, "total_km": 0.0, "total_diesel": 0.0, "intervals_used": 0, "trend": "abhi seekh raha hai"}

    total_km, total_diesel = intervals["km_in_interval"].sum(), intervals["diesel_filled"].sum()

    if total_km < MIN_KM_FOR_ESTIMATE:
        return {
            "avg_kmpl": round(total_km / total_diesel, 2) if total_diesel else 0.0,
            "total_km": round(total_km, 0), "total_diesel": round(total_diesel, 1),
            "intervals_used": len(intervals), "trend": "abhi seekh raha hai",
        }

    avg_kmpl = _robust_weighted_mileage(intervals["mileage"].values, intervals["km_in_interval"].values)

    # ── Trend: data ko chunks mein baant kar pehle vs aakhri chunk ka
    # KM-weighted mileage compare karo ──
    intervals_sorted = intervals.sort_values("interval_end").reset_index(drop=True)
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
        "total_diesel": round(total_diesel, 1), "intervals_used": len(intervals), "trend": trend,
    }


def expected_diesel_cost(estimate: dict, period_expected_km: float,
                          rate_per_litre: float, fallback_kmpl: float = 5.5) -> dict:
    """Data-driven avg_kmpl ko period ke expected KM ke saath combine karke
    Expected Diesel Cost deta hai. Agar bus ke paas abhi kaafi data nahi hai
    (avg_kmpl 0), to `fallback_kmpl` (manual/config default) use hota hai."""
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
        "trend": estimate.get("trend", ""),
    }
