"""
Predictive Maintenance — service records ka "Next Due KM"/"Next Due Date"
manual hota hai, lekin ye module bus ki ACTUAL usage rate (km/din) se
predict karta hai ki wo target kab aayega — fixed calendar assumption
ki jagah real driving pattern use karke.
"""

from datetime import date, timedelta
import pandas as pd


def predict_service_due(next_due_km, next_due_date, km_driven_since_service: float, avg_daily_km: float) -> dict:
    """next_due_km / next_due_date: maintenance record me manually set target
    (dono me se koi ek ya dono ho sakte hain).
    km_driven_since_service: last service ke baad se ab tak kitna chala.
    avg_daily_km: bus ka recent average daily km (usage rate).

    Returns: {} agar kuch predict karne layak nahi, warna:
    {"predicted_due_date": date, "days_remaining": int, "km_remaining": float,
     "basis": str, "urgency": str}"""
    if next_due_km and avg_daily_km and avg_daily_km > 0:
        km_remaining = max(0, next_due_km - km_driven_since_service)
        days_remaining = km_remaining / avg_daily_km
        predicted_date = date.today() + timedelta(days=round(days_remaining))

        if days_remaining <= 3:
            urgency = "🚨 Turant due hai"
        elif days_remaining <= 10:
            urgency = "⚠️ Jald aane wala hai"
        else:
            urgency = "✅ Abhi time hai"

        return {
            "predicted_due_date": predicted_date,
            "days_remaining": round(days_remaining),
            "km_remaining": round(km_remaining),
            "basis": f"Usage rate: {avg_daily_km:.0f} km/din (last 30 din ka average)",
            "urgency": urgency,
        }

    if next_due_date:
        try:
            d = pd.to_datetime(next_due_date).date()
        except (ValueError, TypeError):
            return {}
        days_remaining = (d - date.today()).days
        if days_remaining < 0:
            urgency = "🚨 Overdue"
        elif days_remaining <= 7:
            urgency = "⚠️ Jald aane wala hai"
        else:
            urgency = "✅ Abhi time hai"
        return {
            "predicted_due_date": d,
            "days_remaining": days_remaining,
            "km_remaining": None,
            "basis": "Fixed date (manually set, usage-rate se predict nahi kiya)",
            "urgency": urgency,
        }

    return {}
