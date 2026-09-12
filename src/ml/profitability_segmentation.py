"""
Bus Profitability Segmentation — Income per KM, Diesel Cost per KM, aur
Net Profit ko combine karke har bus ko teen buckets mein daalta hai:
🟢 High Profit / 🟡 Moderate / 🔴 Loss-making.

Rule bahut simple aur explainable rakha gaya hai (koi black-box ML nahi) —
per-km margin (Income/KM − Diesel Cost/KM) ka Income/KM se ratio dekha
jaata hai, taaki bade-fleet aur chhote-fleet bus dono fairly compare ho
sakein (raw Net Profit ka absolute number size-biased hota hai)."""

import pandas as pd


def segment_bus_profitability(df: pd.DataFrame) -> pd.DataFrame:
    """df: columns ['Bus', 'Income_per_KM', 'Diesel_Cost_per_KM', 'Net_Profit'].
    Returns same df + 'Segment' column."""
    df = df.copy()
    if df.empty:
        df["Segment"] = pd.Series(dtype="object")
        return df

    def _segment(row) -> str:
        net           = row.get("Net_Profit", 0) or 0
        income_per_km = row.get("Income_per_KM", 0) or 0
        diesel_per_km = row.get("Diesel_Cost_per_KM", 0) or 0
        margin_per_km = income_per_km - diesel_per_km

        if net <= 0 or margin_per_km <= 0:
            return "🔴 Loss-making"
        if income_per_km > 0 and margin_per_km >= income_per_km * 0.5:
            return "🟢 High Profit"
        return "🟡 Moderate"

    df["Segment"] = df.apply(_segment, axis=1)
    return df
