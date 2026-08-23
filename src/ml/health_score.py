"""
Vehicle Health Score — mileage anomaly, income anomaly, aur maintenance
status ko combine karke har bus ka ek single 0-100 score banata hai.
Dashboard pe ek hi jagah fleet ki overall health dikhane ke liye.
"""


def compute_health_score(avg_mileage_z, avg_income_z, maintenance_overdue_days: int = 0) -> dict:
    """avg_mileage_z / avg_income_z: us bus ke current period ke average
    z-scores (None ho sakta hai agar ML baseline abhi ready nahi).
    maintenance_overdue_days: kitne din se koi service overdue hai (0 = nahi hai).

    Returns: {"score": int (0-100), "label": str, "reasons": list[str]}"""
    score   = 100.0
    reasons = []

    if avg_mileage_z is not None and avg_mileage_z < 0:
        penalty = min(30, abs(avg_mileage_z) * 10)
        score -= penalty
        if penalty > 5:
            reasons.append(f"Mileage average se {abs(avg_mileage_z):.1f}σ neeche hai")

    if avg_income_z is not None and avg_income_z < 0:
        penalty = min(30, abs(avg_income_z) * 10)
        score -= penalty
        if penalty > 5:
            reasons.append(f"Income average se {abs(avg_income_z):.1f}σ neeche hai")

    if maintenance_overdue_days and maintenance_overdue_days > 0:
        penalty = min(40, maintenance_overdue_days * 2)
        score -= penalty
        reasons.append(f"Maintenance {maintenance_overdue_days} din se overdue hai")

    score = max(0, min(100, round(score)))

    if score >= 85:
        label = "🟢 Excellent"
    elif score >= 65:
        label = "🔵 Good"
    elif score >= 40:
        label = "🟠 Needs Attention"
    else:
        label = "🔴 Critical"

    if not reasons:
        reasons.append("Koi bada issue nahi mila")

    return {"score": score, "label": label, "reasons": reasons}


def compute_fleet_health(bus_numbers: list, mileage_z_by_bus: dict, income_z_by_bus: dict,
                          maintenance_overdue_by_bus: dict = None) -> dict:
    """Sab buses ka health score ek saath compute karta hai.
    mileage_z_by_bus / income_z_by_bus: {bus_number: avg_zscore}
    maintenance_overdue_by_bus: {bus_number: overdue_days}
    Returns: {bus_number: {"score":..., "label":..., "reasons":...}}"""
    maintenance_overdue_by_bus = maintenance_overdue_by_bus or {}
    results = {}
    for bus in bus_numbers:
        results[bus] = compute_health_score(
            mileage_z_by_bus.get(bus),
            income_z_by_bus.get(bus),
            maintenance_overdue_by_bus.get(bus, 0),
        )
    return results
