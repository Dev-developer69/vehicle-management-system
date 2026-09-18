import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from src.database.config import supabase, supabase_admin


# ══════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════

def _to_df(rows, rename: dict, cols: list) -> pd.DataFrame:
    """Supabase rows -> renamed/ordered DataFrame; empty rows par bhi sahi columns ke saath khali df deta hai."""
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).rename(columns=rename)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def _safe_int(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if isinstance(val, str) and val.strip() == "":
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════
# VEHICLE RECORDS
# ══════════════════════════════════════════════

def get_scheduled_km(bus_number: str) -> int:
    res = supabase.table("vehicle_scheduled_km").select("scheduled_km").eq("bus_number", bus_number).execute()
    return int(res.data[0]["scheduled_km"] or 466) if res.data else 466


def save_scheduled_km(bus_number: str, scheduled_km: int) -> None:
    supabase_admin.table("vehicle_scheduled_km").upsert(
        {"bus_number": bus_number, "scheduled_km": scheduled_km}, on_conflict="bus_number").execute()


def get_vehicle_payment_config(bus_number: str) -> dict:
    """Payment calculation config — 'standard' (Income - KM×rate - tax) ya
    'ipkm_slab' (IPKM = (Income-tax)/KM; agar IPKM < threshold to
    (IPKM-deduction)×KM, warna (threshold-deduction)×KM). Dono methods ke
    final result me se 1% tax + final_deduction minus hoke Final Payment
    banta hai."""
    res = supabase_admin.table("vehicle_payment_rate").select("*").eq("bus_number", bus_number).execute()
    if res.data:
        r = res.data[0]
        return {
            "rate": float(r.get("rate") or 0), "method": r.get("method") or "standard",
            "ipkm_threshold": float(r.get("ipkm_threshold") or 0),
            "ipkm_deduction": float(r.get("ipkm_deduction") or 0),
            "final_deduction": float(r.get("final_deduction") or 0),
        }
    return {"rate": 0.0, "method": "standard", "ipkm_threshold": 0.0, "ipkm_deduction": 0.0, "final_deduction": 0.0}


def save_vehicle_payment_config(bus_number: str, rate: float, method: str,
                                 ipkm_threshold: float, ipkm_deduction: float, final_deduction: float) -> None:
    supabase_admin.table("vehicle_payment_rate").upsert({
        "bus_number": bus_number, "rate": float(rate), "method": method,
        "ipkm_threshold": float(ipkm_threshold), "ipkm_deduction": float(ipkm_deduction),
        "final_deduction": float(final_deduction),
    }, on_conflict="bus_number").execute()


_COMPLIANCE_FIELDS = [
    "owner_name", "route_name", "capacity",
    "insurance_validity", "fitness_validity", "pollution_validity",
    "road_tax_validity", "registration_date",
]


def get_vehicle_compliance(bus_number: str) -> dict:
    """Bus Report page ke liye — owner/route/capacity + Insurance/Fitness/
    Pollution/Road Tax validity dates (purane Excel sheet jaisa hi data)."""
    res = supabase.table("vehicle_compliance").select("*").eq("bus_number", bus_number).execute()
    if res.data:
        r = res.data[0]
        return {f: r.get(f) for f in _COMPLIANCE_FIELDS}
    return {f: None for f in _COMPLIANCE_FIELDS}


def save_vehicle_compliance(bus_number: str, **fields) -> None:
    payload = {"bus_number": bus_number}
    for f in _COMPLIANCE_FIELDS:
        if f in fields:
            payload[f] = fields[f]
    supabase.table("vehicle_compliance").upsert(payload, on_conflict="bus_number").execute()


def get_km_combines(bus_number: str):
    """Har group: {'id':.., 'dates':[...]}"""
    res = supabase.table("vehicle_km_combines").select("id, dates").eq("bus_number", bus_number).execute()
    groups = []
    for r in (res.data or []):
        try:
            dates = json.loads(r["dates"])
        except (TypeError, ValueError):
            dates = []
        if dates:
            groups.append({"id": r["id"], "dates": dates})
    return groups


def save_km_combine(bus_number: str, dates: list) -> None:
    supabase_admin.table("vehicle_km_combines").insert(
        {"bus_number": bus_number, "dates": json.dumps(sorted(dates))}).execute()


def delete_km_combine(bus_number: str, group_id) -> None:
    supabase_admin.table("vehicle_km_combines").delete().eq("bus_number", bus_number).eq("id", group_id).execute()


def delete_vehicle_record(bus_number: str, date_str: str) -> None:
    supabase.table("vehicle_records").delete().eq("bus_number", bus_number).eq("date", date_str).execute()


def save_vehicle_records(bus_number: str, df: pd.DataFrame, fields_to_update: list = None) -> None:
    """`fields_to_update` (optional): jab conflict-resolution me user sirf
    kuch specific fields hi update karna chahta hai (jaise 'Sirf Driver
    update karo'), yahan un fields ke DB column names ki list do — sirf
    wahi columns naye value se update honge, baaki sab EXISTING (old) DB
    value pe hi rahenge. `None` (default) = purana full-merge behaviour
    (khaali fields purani value rakhte hain, bhari hui fields overwrite)."""
    from src.database.auth import get_current_role
    user = st.session_state.get("user")
    current_email, current_role = (user.email if user else "unknown"), get_current_role()

    def keep(new_val, old_val, empty_vals):
        return new_val if new_val not in empty_vals else old_val

    for _, row in df.iterrows():
        date_str = str(row["Date"])
        on_leave = str(row.get("Status", "Present")).strip() == "On Leave"
        existing = supabase.table("vehicle_records").select("*").eq("bus_number", bus_number).eq("date", date_str).execute()

        new_data = {
            "bus_number": bus_number, "date": date_str, "status": "On Leave" if on_leave else "Present",
            "driver_name": row.get("Driver Name"), "conductor_name": row.get("Conductor Name"),
            "scheduled_km": 0 if on_leave else _safe_int(row.get("Scheduled KM")),
            "actual_km":    0 if on_leave else _safe_int(row.get("Actual KM")),
            "diesel":       None if on_leave else (float(row.get("Diesel")) if pd.notna(row.get("Diesel")) else None),
            "diesel_km":    None if on_leave else _safe_int(row.get("Diesel KM")),
            "income":       None if on_leave else _safe_int(row.get("Income")),
            "gross_income": None if on_leave else _safe_int(row.get("Gross Income")),
            "updated_by": current_email, "updated_by_role": current_role,
            "remark": str(row.get("Remark") or ""), "next_period": bool(row.get("Next", False)),
        }

        if existing.data:
            old = existing.data[0]

            if fields_to_update is not None:
                # ── ✅ Partial save — sirf caller-specified fields update
                # hote hain, baaki SAB old (DB) value pe hi wapas set hote
                # hain (chhede bhi jaate hain taaki update() call consistent
                # rahe, par value change nahi hoti). ──
                merged = {
                    "bus_number": bus_number, "date": date_str,
                    "status": old.get("status", "Present"),
                    "updated_by": current_email, "updated_by_role": current_role,
                    "remark": old.get("remark", ""), "next_period": old.get("next_period", False),
                    "driver_name":    old.get("driver_name"),
                    "conductor_name": old.get("conductor_name"),
                    "scheduled_km":   old.get("scheduled_km"),
                    "actual_km":      old.get("actual_km"),
                    "diesel":         old.get("diesel"),
                    "diesel_km":      old.get("diesel_km"),
                    "income":         old.get("income"),
                    "gross_income":   old.get("gross_income"),
                }
                for f in fields_to_update:
                    if f in new_data:
                        merged[f] = new_data[f]
            else:
                merged = {
                    "bus_number": bus_number, "date": date_str, "status": new_data["status"],
                    "updated_by": current_email, "updated_by_role": current_role,
                    "remark": new_data["remark"] or old.get("remark", ""), "next_period": new_data["next_period"],
                    "driver_name":    keep(new_data["driver_name"],    old.get("driver_name"),    [None, "", "None", "none"]),
                    "conductor_name": keep(new_data["conductor_name"], old.get("conductor_name"), [None, "", "None", "none"]),
                    "scheduled_km": new_data["scheduled_km"] if on_leave else keep(new_data["scheduled_km"], old.get("scheduled_km"), [None]),
                    "actual_km":    new_data["actual_km"]    if on_leave else keep(new_data["actual_km"],    old.get("actual_km"),    [None]),
                    "diesel":       keep(new_data["diesel"],       old.get("diesel"),       [None]),
                    "diesel_km":    keep(new_data["diesel_km"],    old.get("diesel_km"),    [None]),
                    "income":       keep(new_data["income"],       old.get("income"),       [None]),
                    "gross_income": keep(new_data["gross_income"], old.get("gross_income"), [None]),
                }
            supabase.table("vehicle_records").update(merged).eq("bus_number", bus_number).eq("date", date_str).execute()
        else:
            supabase.table("vehicle_records").insert(new_data).execute()


def get_vehicle_records(bus_number: str) -> pd.DataFrame:
    res = supabase.table("vehicle_records").select("*").eq("bus_number", bus_number).order("date", desc=True).execute()
    cols = ["Date", "Status", "Driver Name", "Conductor Name", "Scheduled KM", "Actual KM",
            "Diesel", "Diesel KM", "Income", "Gross Income", "Remark", "Next"]
    df = _to_df(res.data or [], {
        "date": "Date", "status": "Status", "driver_name": "Driver Name", "conductor_name": "Conductor Name",
        "scheduled_km": "Scheduled KM", "actual_km": "Actual KM", "diesel": "Diesel", "diesel_km": "Diesel KM",
        "income": "Income", "gross_income": "Gross Income", "remark": "Remark", "next_period": "Next",
    }, cols)
    for col, default in [("Status", "Present"), ("Remark", ""), ("Next", False), ("Diesel KM", 0), ("Gross Income", 0)]:
        df[col] = df[col].fillna(default) if col in df.columns and not df.empty else df[col]
    return df


def get_diesel_summary(bus_number: str, from_date: str, to_date: str) -> pd.DataFrame:
    res = supabase.table("vehicle_records").select("date, diesel, status") \
        .eq("bus_number", bus_number).gte("date", from_date).lte("date", to_date).order("date").execute()
    if not res.data:
        return pd.DataFrame(columns=["Date", "Diesel"])
    df = pd.DataFrame(res.data)
    df = df[df["status"] != "On Leave"].rename(columns={"date": "Date", "diesel": "Diesel"})
    df["Diesel"] = pd.to_numeric(df["Diesel"], errors="coerce").fillna(0)
    return df[["Date", "Diesel"]]


# ══════════════════════════════════════════════
# SPLIT DUTY — ek din, 2 drivers/conductors ke beech KM ke hisaab se
# duty credit baantna (driver aur conductor independently split ho sakte
# hain — zaroori nahi dono ek saath split ho)
# ══════════════════════════════════════════════

def get_duty_splits(bus_number: str, dates: list = None) -> pd.DataFrame:
    """Split-duty entries laata hai. `dates` diya to sirf unhi dates ke
    liye (Bus Report jaisi period-scoped queries ke liye), warna sab."""
    query = supabase.table("vehicle_duty_splits").select("*").eq("bus_number", bus_number)
    if dates:
        query = query.in_("date", dates)
    res = query.execute()
    cols = ["id", "Date", "Driver 1", "Driver 1 KM", "Driver 2", "Driver 2 KM",
            "Conductor 1", "Conductor 1 KM", "Conductor 2", "Conductor 2 KM"]
    return _to_df(res.data or [], {
        "date": "Date",
        "driver_1": "Driver 1", "driver_1_km": "Driver 1 KM",
        "driver_2": "Driver 2", "driver_2_km": "Driver 2 KM",
        "conductor_1": "Conductor 1", "conductor_1_km": "Conductor 1 KM",
        "conductor_2": "Conductor 2", "conductor_2_km": "Conductor 2 KM",
    }, cols)


def save_duty_split(bus_number: str, date_str: str,
                     driver_1: str = "", driver_1_km: float = 0,
                     driver_2: str = "", driver_2_km: float = 0,
                     conductor_1: str = "", conductor_1_km: float = 0,
                     conductor_2: str = "", conductor_2_km: float = 0) -> None:
    """Ek din ke split-duty ko upsert karta hai. Driver split aur Conductor
    split dono independent hain — sirf driver ka bhar sakte ho, ya sirf
    conductor ka, ya dono (jaisa jis din jo situation ho)."""
    supabase.table("vehicle_duty_splits").upsert({
        "bus_number": bus_number, "date": date_str,
        "driver_1": (driver_1 or "").strip(), "driver_1_km": float(driver_1_km or 0),
        "driver_2": (driver_2 or "").strip(), "driver_2_km": float(driver_2_km or 0),
        "conductor_1": (conductor_1 or "").strip(), "conductor_1_km": float(conductor_1_km or 0),
        "conductor_2": (conductor_2 or "").strip(), "conductor_2_km": float(conductor_2_km or 0),
    }, on_conflict="bus_number,date").execute()


def delete_duty_split(bus_number: str, date_str: str) -> None:
    supabase.table("vehicle_duty_splits").delete().eq("bus_number", bus_number).eq("date", date_str).execute()


def compute_role_duty_credits(vr: pd.DataFrame, splits_df: pd.DataFrame, role: str) -> dict:
    """Ek role ('driver' ya 'conductor') ke liye har naam ka total duty
    credit nikalta hai:
      - agar us date ka split-entry hai (dono naam + KM bhare hue) → dono
        logon ko unka_km / total_km ka fractional credit
      - warna → us date ke normal Driver/Conductor Name field wale insaan
        ko poora 1.0 duty credit (jaisa split ke bina hamesha se hota tha)
    Returns {name: total_duty_credit}."""
    name_col = "Driver Name" if role == "driver" else "Conductor Name"
    prefix   = "Driver" if role == "driver" else "Conductor"
    p1_col, p1km_col = f"{prefix} 1", f"{prefix} 1 KM"
    p2_col, p2km_col = f"{prefix} 2", f"{prefix} 2 KM"

    split_by_date = {}
    if not splits_df.empty:
        for _, r in splits_df.iterrows():
            p1, p1km = str(r.get(p1_col) or "").strip(), float(r.get(p1km_col) or 0)
            p2, p2km = str(r.get(p2_col) or "").strip(), float(r.get(p2km_col) or 0)
            if p1 and p2 and (p1km + p2km) > 0:
                split_by_date[str(r["Date"])] = [(p1, p1km), (p2, p2km)]

    credits = {}
    if vr.empty:
        return credits

    # ✅ Case-insensitive merge — "Avdhesh" aur "avdhesh" do alag entries
    # nahi banni chahiye. Har naam ke lowercase-key ke liye pehli baar jo
    # casing mili wahi consistently use hoti hai, taaki saari credit ek hi
    # entry me jama ho.
    _JUNK_NAMES = ("none", "", "no", "test")
    display_names: dict[str, str] = {}

    def _add_credit(name: str, amount: float) -> None:
        name = (name or "").strip()
        if not name or name.lower() in _JUNK_NAMES:
            return
        key = name.lower()
        canon = display_names.setdefault(key, name)
        credits[canon] = credits.get(canon, 0.0) + amount

    duty_df = vr[vr["Status"] != "On Leave"]
    for _, row in duty_df.iterrows():
        date_str = str(row["Date"])
        if date_str in split_by_date:
            people = split_by_date[date_str]
            total_km = sum(km for _, km in people) or 1  # div/0 se bachao
            for name, km in people:
                _add_credit(name, km / total_km)
        else:
            _add_credit(str(row.get(name_col) or ""), 1.0)
    return credits


# ══════════════════════════════════════════════
# DIESEL RATE + PAYMENT (universal), PER-ROW RATE
# ══════════════════════════════════════════════

def _lookup_credit(credits: dict, name: str) -> float:
    """compute_role_duty_credits ke return-dict me case-insensitive lookup —
    kyunki credits dict ki canonical casing (first-seen) aur caller ke paas
    jo naam hai (jaise get_drivers_for_buses ka most-common casing) kabhi
    match nahi bhi kar sakte, jisse exact-match .get() silently 0.0de deta."""
    key = (name or "").strip().lower()
    for k, v in credits.items():
        if k.strip().lower() == key:
            return v
    return 0.0


def get_diesel_rate_payment(bus_number: str, month: int, period: str) -> dict:
    res = supabase_admin.table("diesel_details").select("rate, paid_amount, payment_done") \
        .eq("bus_number", bus_number).eq("month", month).eq("period", period).execute()
    if res.data:
        r = res.data[0]
        return {"rate": float(r["rate"] or 95.69), "paid_amount": float(r["paid_amount"] or 0), "payment_done": bool(r["payment_done"])}
    return {"rate": 95.69, "paid_amount": 0.0, "payment_done": False}


def save_diesel_rate_payment(bus_number: str, month: int, period: str, rate: float, paid_amount: float, payment_done: bool) -> None:
    supabase_admin.table("diesel_details").upsert({
        "bus_number": bus_number, "month": month, "period": period,
        "rate": rate, "paid_amount": paid_amount, "payment_done": payment_done,
    }, on_conflict="bus_number,month,period").execute()


def get_diesel_row_rates(bus_number: str, dates: list) -> dict:
    if not dates:
        return {}
    res = supabase_admin.table("diesel_row_rates").select("date, rate").eq("bus_number", bus_number).in_("date", dates).execute()
    return {row["date"]: float(row["rate"]) for row in res.data} if res.data else {}


def save_diesel_row_rate(bus_number: str, row_date: str, rate: float) -> None:
    supabase_admin.table("diesel_row_rates").upsert(
        {"bus_number": bus_number, "date": row_date, "rate": rate}, on_conflict="bus_number,date").execute()


# ══════════════════════════════════════════════
# FUEL FILLS (CNG/Diesel — multiple entries per date allowed)
# ══════════════════════════════════════════════

def _sync_vehicle_record_diesel(bus_number: str, date_str: str) -> None:
    """Us din ka fuel_fills total nikal ke vehicle_records.diesel (agar row exist kare) me sync karta hai."""
    fills = supabase.table("fuel_fills").select("quantity").eq("bus_number", bus_number).eq("date", date_str).execute()
    total_qty = sum(float(r["quantity"] or 0) for r in (fills.data or []))
    existing = supabase.table("vehicle_records").select("id").eq("bus_number", bus_number).eq("date", date_str).execute()
    if existing.data:
        supabase.table("vehicle_records").update({"diesel": total_qty}).eq("bus_number", bus_number).eq("date", date_str).execute()


def save_fuel_fill(bus_number: str, fill_date: str, quantity: float, rate: float) -> None:
    """Naya fill insert (same date pe dobara call = alag row, overwrite nahi)."""
    supabase.table("fuel_fills").insert(
        {"bus_number": bus_number, "date": fill_date, "quantity": float(quantity), "rate": float(rate)}).execute()
    _sync_vehicle_record_diesel(bus_number, fill_date)


def get_fuel_fills(bus_number: str, from_date: str, to_date: str) -> pd.DataFrame:
    res = supabase.table("fuel_fills").select("*").eq("bus_number", bus_number) \
        .gte("date", from_date).lte("date", to_date).order("date").order("created_at").execute()
    return _to_df(res.data or [], {"date": "Date", "quantity": "Quantity", "rate": "Rate", "amount": "Amount"},
                  ["id", "Date", "Quantity", "Rate", "Amount"])


def update_fuel_fill(bus_number: str, fill_id, updates: dict) -> None:
    existing = supabase.table("fuel_fills").select("date").eq("id", fill_id).execute()
    old_date = existing.data[0]["date"] if existing.data else None
    rename = {"Date": "date", "Quantity": "quantity", "Rate": "rate"}
    db_updates = {rename.get(k, k): v for k, v in updates.items() if k in rename}
    if db_updates:
        supabase.table("fuel_fills").update(db_updates).eq("id", fill_id).execute()
    if old_date:
        _sync_vehicle_record_diesel(bus_number, old_date)
    new_date = db_updates.get("date")
    if new_date and new_date != old_date:
        _sync_vehicle_record_diesel(bus_number, new_date)


def delete_fuel_fill(bus_number: str, fill_id) -> None:
    existing = supabase.table("fuel_fills").select("date").eq("id", fill_id).execute()
    fill_date = existing.data[0]["date"] if existing.data else None
    supabase.table("fuel_fills").delete().eq("id", fill_id).execute()
    if fill_date:
        _sync_vehicle_record_diesel(bus_number, fill_date)


def clear_fuel_fills_for_date(bus_number: str, date_str: str) -> int:
    """Explicit '0' fill par — us date ki saari entries reset/delete karta hai."""
    existing = supabase.table("fuel_fills").select("id").eq("bus_number", bus_number).eq("date", date_str).execute()
    rows = existing.data or []
    if not rows:
        return 0
    supabase.table("fuel_fills").delete().eq("bus_number", bus_number).eq("date", date_str).execute()
    _sync_vehicle_record_diesel(bus_number, date_str)
    return len(rows)


def get_existing_fuel_fill_dates(bus_number: str, dates: list) -> set:
    if not dates:
        return set()
    res = supabase.table("fuel_fills").select("date").eq("bus_number", bus_number).in_("date", dates).execute()
    return {r["date"] for r in (res.data or [])}


def replace_fuel_fill_for_date(bus_number: str, date_str: str, quantity: float, rate: float) -> None:
    """'Yes, Update' — purani saari entries hata ke ek nayi (total) daal deta hai."""
    supabase.table("fuel_fills").delete().eq("bus_number", bus_number).eq("date", date_str).execute()
    supabase.table("fuel_fills").insert(
        {"bus_number": bus_number, "date": date_str, "quantity": float(quantity), "rate": float(rate)}).execute()
    _sync_vehicle_record_diesel(bus_number, date_str)


def get_unmigrated_diesel_dates(bus_number: str) -> list:
    """Dates jinka vehicle_records.diesel bhara hai par fuel_fills me abhi entry nahi hai."""
    records = supabase.table("vehicle_records").select("date, diesel").eq("bus_number", bus_number).gt("diesel", 0).execute()
    rows = records.data or []
    if not rows:
        return []
    dates = [r["date"] for r in rows]
    existing = supabase.table("fuel_fills").select("date").eq("bus_number", bus_number).in_("date", dates).execute()
    already = {r["date"] for r in (existing.data or [])}
    return [r["date"] for r in rows if r["date"] not in already]


def migrate_diesel_to_fuel_fills(bus_number: str) -> int:
    """Legacy vehicle_records.diesel -> fuel_fills copy (per-date, duplicate-safe, dobara chalane par bhi safe)."""
    records = supabase.table("vehicle_records").select("date, diesel").eq("bus_number", bus_number).gt("diesel", 0).execute()
    rows = records.data or []
    if not rows:
        return 0
    dates = [r["date"] for r in rows]
    existing = supabase.table("fuel_fills").select("date").eq("bus_number", bus_number).in_("date", dates).execute()
    already = {r["date"] for r in (existing.data or [])}
    inserted = 0
    for r in rows:
        if r["date"] in already:
            continue
        qty = float(r["diesel"] or 0)
        if qty <= 0:
            continue
        rate = get_diesel_row_rates(bus_number, [r["date"]]).get(r["date"]) or 95.69
        supabase.table("fuel_fills").insert(
            {"bus_number": bus_number, "date": r["date"], "quantity": qty, "rate": rate}).execute()
        inserted += 1
    return inserted


# ══════════════════════════════════════════════
# DRIVER SALARY
# ══════════════════════════════════════════════

def save_driver_salary(df: pd.DataFrame, bus_number: str = "") -> None:
    user = st.session_state.get("user")
    updated_by = user.email if user else "unknown"
    records = []
    for _, row in df.iterrows():
        try:
            salary_val = float(str(row["Salary"]).replace(",", "").strip() or 0)
        except (ValueError, TypeError):
            salary_val = 0.0
        txn_val = str(row.get("Transaction") or "").strip().lower()
        txn_val = txn_val if txn_val in ("cash", "online") else "cash"
        records.append({
            "driver_name": str(row["Driver Name"]).strip(), "date": str(row["Date"]),
            "salary": salary_val, "transaction": txn_val, "bus_number": bus_number,
            "updated_by": updated_by, "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    if not records:
        return
    try:
        supabase.table("driver_salary").insert(records).execute()
    except Exception as e:
        log_error("save_driver_salary", str(e), bus_number=bus_number, extra_data=str(records))
        st.error("⚠️ Save failed — error logged.")


def get_driver_salary(bus_number: str = "") -> pd.DataFrame:
    query = supabase.table("driver_salary").select("*").order("date", desc=True)
    if bus_number:
        query = query.eq("bus_number", bus_number)
    df = _to_df(query.execute().data or [],
                {"date": "Date", "driver_name": "Driver Name", "salary": "Salary", "transaction": "Transaction", "updated_by": "Updated By"},
                ["id", "Date", "Driver Name", "Salary", "Transaction", "Updated By"])
    if not df.empty:
        df["Updated By"] = df["Updated By"].fillna("")
    return df


def get_salary_check(from_date: str = None, to_date: str = None, bus_numbers: list = None) -> pd.DataFrame:
    query = supabase.table("vehicle_records").select("driver_name, bus_number, date, status")
    if from_date: query = query.gte("date", from_date)
    if to_date: query = query.lte("date", to_date)
    if bus_numbers: query = query.in_("bus_number", bus_numbers)
    res = query.execute()
    empty = pd.DataFrame(columns=["Sr No", "Driver Name", "Bus Number", "Duties", "Salary Due", "Salary Given", "Remaining"])
    if not res.data:
        return empty

    df = pd.DataFrame(res.data)
    df = df[df.get("status", "Present") != "On Leave"]
    # ✅ Yahan driver_name field ke basis pe rows ko drop NAHI karte (jaise
    # pehle "no"/"test"/"none" wale turant discard ho jaate the) — kyunki
    # split-duty wale din ka raw Driver Name field abhi bhi default "None"
    # ho sakta hai (agar sirf Split Duty section use kiya ho, main grid ka
    # field edit na kiya ho). Aisi row discard hone se us din ka split
    # credit hi dono logon ko miss ho jaata tha. Junk-name filtering ab
    # neeche compute_role_duty_credits ke andar hoti hai — jo sirf
    # non-split dates par hi driver_name field dekhta hai. ──

    # ── Split-duty aware duty count — normal dates 1.0 duty, split-duty
    # dates KM ke fraction ke hisaab se (bus-wise, kyunki split bus+date
    # specific hota hai) ──
    dates_involved = df["date"].unique().tolist()
    bus_list = bus_numbers if bus_numbers else df["bus_number"].dropna().unique().tolist()
    splits_by_bus = {b: get_duty_splits(b, dates_involved) for b in bus_list}

    duty_rows = []
    for bus, bus_df in df.groupby("bus_number"):
        vr_like = bus_df.rename(columns={"driver_name": "Driver Name", "date": "Date"}).copy()
        vr_like["Status"] = "Present"
        credits = compute_role_duty_credits(vr_like, splits_by_bus.get(bus, pd.DataFrame()), "driver")
        for name, duties in credits.items():
            duty_rows.append({"driver_name": name, "bus_number": bus, "duties": duties})

    if not duty_rows:
        return empty
    grouped = pd.DataFrame(duty_rows)
    grouped["key"] = grouped["driver_name"].str.strip().str.lower() + "_" + grouped["bus_number"].fillna("")

    # ── Salary given ──
    sal_query = supabase.table("driver_salary").select("driver_name, salary, bus_number, date")
    if from_date: sal_query = sal_query.gte("date", from_date)
    if to_date: sal_query = sal_query.lte("date", to_date)
    if bus_numbers: sal_query = sal_query.in_("bus_number", bus_numbers)
    sal_res = sal_query.execute()
    sal_df = pd.DataFrame(sal_res.data) if sal_res.data else pd.DataFrame(columns=["driver_name", "salary", "bus_number", "date"])
    if not sal_df.empty:
        sal_df["key"] = sal_df["driver_name"].str.strip().str.lower() + "_" + sal_df["bus_number"].fillna("")
        grouped = grouped.merge(sal_df.groupby("key")["salary"].sum().reset_index(), on="key", how="left")
        grouped["salary"] = grouped["salary"].fillna(0)
    else:
        grouped["salary"] = 0

    # ── Rate: specific-bus rate, warna 'ALL vehicles' fallback ──
    rates_res = supabase.table("driver_salary_rates").select("driver_name, bus_number, rate").execute()
    rates_df = pd.DataFrame(rates_res.data) if rates_res.data else pd.DataFrame(columns=["driver_name", "bus_number", "rate"])
    if not rates_df.empty:
        rates_df["driver_key"] = rates_df["driver_name"].str.strip().str.lower()
        rates_df["key"] = rates_df["driver_key"] + "_" + rates_df["bus_number"].fillna("")
        specific = rates_df[rates_df["bus_number"] != "ALL"].groupby("key")["rate"].first()
        allrate  = rates_df[rates_df["bus_number"] == "ALL"].groupby("driver_key")["rate"].first()
        grouped["driver_key"] = grouped["driver_name"].str.strip().str.lower()
        grouped["rate"] = grouped["key"].map(specific).fillna(grouped["driver_key"].map(allrate)).fillna(0)
    else:
        grouped["rate"] = 0

    grouped["salary_due"] = grouped["duties"] * grouped["rate"]
    grouped["remaining"]  = grouped["salary_due"] - grouped["salary"]
    grouped["duties"]     = grouped["duties"].round(2)
    grouped = grouped[["driver_name", "bus_number", "duties", "salary_due", "salary", "remaining"]]
    grouped.columns = ["Driver Name", "Bus Number", "Duties", "Salary Due", "Salary Given", "Remaining"]
    grouped.insert(0, "Sr No", range(1, len(grouped) + 1))
    return grouped


# ══════════════════════════════════════════════
# DRIVER SALARY RATE
# ══════════════════════════════════════════════

def get_driver_rate(bus_number: str, driver_name: str) -> float:
    # ✅ ilike (case-insensitive) — "Avdhesh" ke liye rate set hui ho aur
    # kahin "avdhesh" casing se lookup ho, tab bhi match milna chahiye.
    res = supabase.table("driver_salary_rates").select("rate").eq("bus_number", bus_number).ilike("driver_name", driver_name).execute()
    if res.data:
        return float(res.data[0]["rate"] or 0)
    if bus_number != "ALL":  # ✅ 'ALL vehicles' rate fallback
        res_all = supabase.table("driver_salary_rates").select("rate").eq("bus_number", "ALL").ilike("driver_name", driver_name).execute()
        if res_all.data:
            return float(res_all.data[0]["rate"] or 0)
    return 0.0


def save_driver_rate(bus_number: str, driver_name: str, rate: float, updated_by: str) -> None:
    supabase.table("driver_salary_rates").upsert({
        "bus_number": bus_number, "driver_name": driver_name.strip(), "rate": float(rate), "updated_by": updated_by,
    }, on_conflict="bus_number,driver_name").execute()


def get_all_driver_rates(bus_numbers: list = None) -> pd.DataFrame:
    query = supabase.table("driver_salary_rates").select("*").order("driver_name")
    if bus_numbers:
        query = query.in_("bus_number", bus_numbers)
    return _to_df(query.execute().data or [], {"bus_number": "Bus Number", "driver_name": "Driver Name", "rate": "Rate"},
                  ["Bus Number", "Driver Name", "Rate"])


def get_drivers_for_buses(bus_numbers: list = None) -> list:
    query = supabase.table("vehicle_records").select("driver_name, bus_number")
    if bus_numbers:
        query = query.in_("bus_number", bus_numbers)
    res = query.execute()
    if not res.data:
        return []
    # ✅ Case-insensitive dedup — "Avdhesh" aur "avdhesh" alag-alag dropdown
    # entries na bane. Har lowercase-key ke liye jo casing sabse zyada baar
    # aayi hai wahi final naam banega (taaki koi ek random casing na ban
    # jaaye).
    from collections import Counter
    casing_counts: dict[str, Counter] = {}
    for r in res.data:
        raw = (r.get("driver_name") or "").strip()
        if not raw or raw.lower() in ("no", "test", "none", ""):
            continue
        key = raw.lower()
        casing_counts.setdefault(key, Counter())[raw] += 1
    names = {counter.most_common(1)[0][0] for counter in casing_counts.values()}
    return sorted(names)


def rename_driver(old_name: str, new_name: str) -> dict:
    """Ek driver ka naam saari tables (vehicle_records, salary, rate, license) me merge karta hai — typo/duplicate fix ke liye."""
    old_name, new_name = old_name.strip(), new_name.strip()
    if not old_name or not new_name or old_name.lower() == new_name.lower():
        return {"vehicle_records": 0, "driver_salary": 0, "driver_salary_rates": 0, "drivers": 0}

    counts = {}
    res = supabase.table("vehicle_records").select("bus_number, date").ilike("driver_name", old_name).execute()
    counts["vehicle_records"] = len(res.data or [])
    if counts["vehicle_records"]:
        supabase.table("vehicle_records").update({"driver_name": new_name}).ilike("driver_name", old_name).execute()

    res = supabase.table("driver_salary").select("id").ilike("driver_name", old_name).execute()
    ids = [r["id"] for r in (res.data or [])]
    if ids:
        supabase.table("driver_salary").update({"driver_name": new_name}).in_("id", ids).execute()
    counts["driver_salary"] = len(ids)

    res = supabase.table("driver_salary_rates").select("bus_number").ilike("driver_name", old_name).execute()
    updated = 0
    for bus in [r["bus_number"] for r in (res.data or [])]:
        existing = supabase.table("driver_salary_rates").select("driver_name").eq("driver_name", new_name).eq("bus_number", bus).execute()
        if existing.data:
            supabase.table("driver_salary_rates").delete().ilike("driver_name", old_name).eq("bus_number", bus).execute()
        else:
            supabase.table("driver_salary_rates").update({"driver_name": new_name}).ilike("driver_name", old_name).eq("bus_number", bus).execute()
            updated += 1
    counts["driver_salary_rates"] = updated

    res = supabase.table("drivers").select("driver_name").ilike("driver_name", old_name).execute()
    if res.data:
        existing = supabase.table("drivers").select("driver_name").eq("driver_name", new_name).execute()
        supabase.table("drivers").delete().ilike("driver_name", old_name).execute() if existing.data else \
            supabase.table("drivers").update({"driver_name": new_name}).ilike("driver_name", old_name).execute()
        counts["drivers"] = 1
    else:
        counts["drivers"] = 0
    return counts


# ══════════════════════════════════════════════
# DRIVER LICENSE INFO + FULL DRIVER REPORT
# ══════════════════════════════════════════════

def get_driver_license(driver_name: str) -> dict:
    res = supabase.table("drivers").select("license_number, license_validity, phone").eq("driver_name", driver_name.strip()).execute()
    if res.data:
        r = res.data[0]
        return {"license_number": r.get("license_number") or "", "license_validity": r.get("license_validity"), "phone": r.get("phone") or ""}
    return {"license_number": "", "license_validity": None, "phone": ""}


def save_driver_license(driver_name: str, license_number: str, license_validity, phone: str = "") -> None:
    supabase.table("drivers").upsert({
        "driver_name": driver_name.strip(), "license_number": license_number.strip(),
        "license_validity": str(license_validity) if license_validity else None, "phone": phone.strip(),
    }, on_conflict="driver_name").execute()


def get_driver_report(driver_name: str, from_date: str, to_date: str) -> dict:
    """Ek driver ka poora monthly report — buses, duties, diesel/mileage, income, salary due/given/remaining."""
    driver_key = driver_name.strip().lower()
    res = supabase.table("vehicle_records") \
        .select("driver_name, bus_number, date, status, actual_km, scheduled_km, diesel, diesel_km, income") \
        .gte("date", from_date).lte("date", to_date).execute()
    all_rows = res.data or []

    # ── Split-duty aware involvement check — sirf 'driver_name field ==
    # exact naam' se match nahi karta, kyunki split-duty wale din raw
    # driver_name field me combined/manual text ho sakta hai. Har bus ke
    # us date-range ke splits pehle se fetch kar lo, phir check karo ki
    # driver_key naam field se match karta hai YA kisi date ke split-entry
    # ka Driver 1/2 hai. ──
    bus_dates_in_range = {}
    for r in all_rows:
        bus_dates_in_range.setdefault(r["bus_number"], set()).add(r["date"])
    splits_by_bus = {
        bus: get_duty_splits(bus, list(dates)) for bus, dates in bus_dates_in_range.items()
    }

    def _row_involves_driver(r) -> bool:
        if (r.get("driver_name") or "").strip().lower() == driver_key:
            return True
        splits = splits_by_bus.get(r["bus_number"], pd.DataFrame())
        if splits.empty:
            return False
        match = splits[splits["Date"].astype(str) == str(r["date"])]
        if match.empty:
            return False
        row0 = match.iloc[0]
        names = {
            str(row0.get("Driver 1") or "").strip().lower(),
            str(row0.get("Driver 2") or "").strip().lower(),
        }
        return driver_key in names

    my_rows = [r for r in all_rows if _row_involves_driver(r)]

    empty = {
        "duties_by_bus": {}, "total_duties": 0, "buses": [], "total_actual_km": 0, "total_scheduled_km": 0,
        "total_diesel": 0.0, "total_diesel_km": 0, "avg_mileage": 0.0, "total_income": 0,
        "salary_due": 0.0, "salary_given": 0.0, "remaining": 0.0,
        "daily_log": pd.DataFrame(columns=["Date", "Bus", "Status", "Actual KM", "Diesel", "Income"]),
    }
    if not my_rows:
        return empty

    df = pd.DataFrame(my_rows)
    df = df[df["status"] != "On Leave"]
    for c in ["actual_km", "scheduled_km", "diesel", "diesel_km", "income"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if df.empty:
        return empty

    # ── Split-duty wale din, poore din ka total actual_km nahi — sirf is
    # driver ka apna KM-share (splits table se) dikhana/count karna hai,
    # taaki "kitna khud chalaya" sahi se pata chale, na ki poora din double
    # na ho jaaye dono drivers ke reports me. ──
    def _driver_km_for_split(bus, date_str, default_km):
        splits = splits_by_bus.get(bus, pd.DataFrame())
        if splits.empty:
            return default_km
        match = splits[splits["Date"].astype(str) == str(date_str)]
        if match.empty:
            return default_km
        row0 = match.iloc[0]
        p1, p1km = str(row0.get("Driver 1") or "").strip().lower(), float(row0.get("Driver 1 KM") or 0)
        p2, p2km = str(row0.get("Driver 2") or "").strip().lower(), float(row0.get("Driver 2 KM") or 0)
        if driver_key == p1:
            return p1km
        if driver_key == p2:
            return p2km
        return default_km

    df["actual_km"] = df.apply(
        lambda r: _driver_km_for_split(r["bus_number"], r["date"], r["actual_km"]), axis=1
    )

    # ── Split-duty aware duty credit (bus-wise, kyunki split bus+date
    # specific hota hai) — normal dates 1.0, split dates KM-fraction ──
    duties_by_bus = {}
    for bus, bus_df in df.groupby("bus_number"):
        splits = splits_by_bus.get(bus, pd.DataFrame())
        vr_like = bus_df.rename(columns={"driver_name": "Driver Name", "date": "Date"}).copy()
        vr_like["Status"] = "Present"
        credits = compute_role_duty_credits(vr_like, splits, "driver")
        duties_by_bus[bus] = _lookup_credit(credits, driver_name)

    diesel_rows = df[df["diesel"] > 0]
    total_diesel, total_diesel_km = diesel_rows["diesel"].sum(), diesel_rows["diesel_km"].sum()

    salary_due = sum(duties * get_driver_rate(bus, driver_name) for bus, duties in duties_by_bus.items())
    sal_res = supabase.table("driver_salary").select("driver_name, salary, date").gte("date", from_date).lte("date", to_date).execute()
    salary_given = sum(float(r["salary"] or 0) for r in (sal_res.data or []) if (r.get("driver_name") or "").strip().lower() == driver_key)

    daily_log = df[["date", "bus_number", "status", "actual_km", "diesel", "income"]].sort_values("date", ascending=False).copy()
    daily_log.columns = ["Date", "Bus", "Status", "Actual KM", "Diesel", "Income"]

    total_duties = round(sum(duties_by_bus.values()), 2)
    return {
        "duties_by_bus": duties_by_bus, "total_duties": total_duties, "buses": sorted(duties_by_bus.keys()),
        "total_actual_km": df["actual_km"].sum(), "total_scheduled_km": df["scheduled_km"].sum(),
        "total_diesel": total_diesel, "total_diesel_km": total_diesel_km,
        "avg_mileage": round(total_diesel_km / total_diesel, 2) if total_diesel > 0 else 0.0,
        "total_income": df["income"].sum(), "salary_due": salary_due, "salary_given": salary_given,
        "remaining": salary_due - salary_given, "daily_log": daily_log,
    }


# ══════════════════════════════════════════════
# VEHICLE EXPENSES
# ══════════════════════════════════════════════

def save_vehicle_expenses(bus_number: str, df: pd.DataFrame) -> None:
    records = [{
        "bus_number": bus_number, "date": str(row["Date"]), "category": row["Category"].strip(),
        "amount": float(row["Amount"] or 0), "description": row["Description"] or "",
    } for _, row in df.iterrows()]
    supabase.table("vehicle_expenses").insert(records).execute()


def get_vehicle_expenses(bus_number: str) -> pd.DataFrame:
    res = supabase.table("vehicle_expenses").select("*").eq("bus_number", bus_number).order("date", desc=True).execute()
    return _to_df(res.data or [], {"date": "Date", "category": "Category", "amount": "Amount", "description": "Description"},
                  ["id", "Date", "Category", "Amount", "Description"])


def update_vehicle_expense(expense_id: str, updates: dict) -> None:
    rename = {"Date": "date", "Category": "category", "Amount": "amount", "Description": "description"}
    supabase.table("vehicle_expenses").update({rename.get(k, k): v for k, v in updates.items()}).eq("id", expense_id).execute()


def delete_vehicle_expense(expense_id: str) -> None:
    supabase.table("vehicle_expenses").delete().eq("id", expense_id).execute()


def log_error(function_name: str, error_message: str, bus_number: str = "", extra_data: str = "") -> None:
    try:
        supabase_admin.table("error_logs").insert({
            "function_name": function_name, "bus_number": bus_number,
            "error_message": str(error_message), "extra_data": extra_data,
        }).execute()
    except Exception:
        pass


def update_driver_salary(record_id: str, updates: dict) -> None:
    rename = {"Date": "date", "Driver Name": "driver_name", "Salary": "salary", "Transaction": "transaction"}
    supabase.table("driver_salary").update({rename.get(k, k): v for k, v in updates.items()}).eq("id", record_id).execute()


def delete_driver_salary(record_id: str) -> None:
    supabase.table("driver_salary").delete().eq("id", record_id).execute()


# ══════════════════════════════════════════════
# SUPPLIERS / PRODUCTS / REQUIREMENTS
# ══════════════════════════════════════════════

def get_suppliers() -> pd.DataFrame:
    res = supabase_admin.table("suppliers").select("*").order("name").execute()
    df = _to_df(res.data or [], {"name": "Name", "phone": "Phone", "address": "Address", "remark": "Remark"},
                ["id", "Name", "Phone", "Address", "Remark"])
    if not df.empty:
        df["Remark"] = df["Remark"].fillna("")
    return df


def save_supplier(name: str, phone: str, address: str, remark: str = "") -> tuple:
    name, phone = name.strip(), (phone.strip() if phone else "")
    if not phone:
        return False, "no_phone"
    if supabase_admin.table("suppliers").select("id").ilike("name", name).execute().data:
        return False, "duplicate"
    supabase_admin.table("suppliers").insert({
        "name": name, "phone": phone, "address": (address or "").strip(), "remark": (remark or "").strip(),
    }).execute()
    return True, ""


def delete_supplier(supplier_id: str) -> None:
    supabase_admin.table("suppliers").delete().eq("id", supplier_id).execute()


def get_supplier_products(supplier_id: str) -> pd.DataFrame:
    res = supabase_admin.table("products").select("*").eq("supplier_id", supplier_id).order("purchased_date", desc=True).execute()
    return _to_df(res.data or [], {"name": "Name", "mrp": "MRP", "latest_price": "Latest Price",
                                    "old_price": "Old Price", "purchased_date": "Purchased Date"},
                  ["Name", "Latest Price", "Old Price", "MRP", "Purchased Date"])


def get_products(search: str = "") -> pd.DataFrame:
    res = supabase_admin.table("products").select("*, suppliers(name)").order("name").execute()
    cols = ["id", "Name", "MRP", "Latest Price", "Old Price", "Quantity", "Remark", "Supplier", "Purchased Date"]
    if not res.data:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(res.data)
    df["Supplier"] = df["suppliers"].apply(lambda x: x["name"] if isinstance(x, dict) else "")
    df = df.rename(columns={"name": "Name", "mrp": "MRP", "latest_price": "Latest Price", "old_price": "Old Price",
                             "purchased_date": "Purchased Date", "quantity": "Quantity", "remark": "Remark"})
    df["Quantity"], df["Remark"] = df["Quantity"].fillna(""), df["Remark"].fillna("")
    if search:
        df = df[df["Name"].str.lower().str.contains(search.lower(), na=False)]
    return df[cols]


def save_product(name: str, latest_price: float, mrp: float, supplier_id: str, purchased_date: str,
                  quantity: str = "", remark: str = "") -> None:
    name = name.strip()
    existing = supabase_admin.table("products").select("*").eq("name", name).execute()
    if existing.data:
        old = existing.data[0]
        supabase_admin.table("products").update({
            "old_price": old.get("latest_price"), "latest_price": latest_price,
            "mrp": mrp if mrp else old.get("mrp"), "supplier_id": supplier_id if supplier_id else old.get("supplier_id"),
            "purchased_date": purchased_date, "quantity": quantity or old.get("quantity", ""),
            "remark": remark or old.get("remark", ""),
        }).eq("name", name).execute()
    else:
        supabase_admin.table("products").insert({
            "name": name, "mrp": mrp, "latest_price": latest_price, "old_price": None,
            "supplier_id": supplier_id or None, "purchased_date": purchased_date, "quantity": quantity, "remark": remark,
        }).execute()


def delete_product(product_id: str) -> None:
    supabase_admin.table("products").delete().eq("id", product_id).execute()


def get_requirements() -> pd.DataFrame:
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    supabase_admin.table("product_requirements").delete().eq("fulfilled", True).lt("created_at", week_ago).execute()
    res = supabase_admin.table("product_requirements").select("*").order("created_at", desc=True).execute()
    df = _to_df(res.data or [], {"product_name": "Product Name", "quantity": "Quantity", "remark": "Remark",
                                  "fulfilled": "Fulfilled", "created_at": "Created"},
                ["id", "Product Name", "Quantity", "Remark", "Fulfilled", "Created"])
    if not df.empty:
        df["Created"] = pd.to_datetime(df["Created"]).dt.strftime("%Y-%m-%d")
    return df


def save_requirement(product_name: str, quantity: str, remark: str) -> None:
    supabase_admin.table("product_requirements").insert({
        "product_name": product_name.strip(), "quantity": quantity.strip(), "remark": remark.strip(), "fulfilled": False,
    }).execute()


def fulfill_requirement(req_id: str, product_name: str, latest_price: float, mrp: float, supplier_id: str, purchased_date: str) -> None:
    save_product(product_name, latest_price, mrp, supplier_id, purchased_date)
    supabase_admin.table("product_requirements").update({"fulfilled": True}).eq("id", req_id).execute()


def delete_requirement(req_id: str) -> None:
    supabase_admin.table("product_requirements").delete().eq("id", req_id).execute()


# ══════════════════════════════════════════════
# MAINTENANCE RECORDS
# ══════════════════════════════════════════════

def get_maintenance_records(bus_number: str) -> pd.DataFrame:
    res = supabase.table("maintenance_records").select("*").eq("bus_number", bus_number).order("record_date", desc=True).execute()
    df = _to_df(res.data or [], {
        "record_date": "Date", "service_type": "Service Type", "garage_name": "Garage", "labour_cost": "Labour Cost",
        "item_cost": "Item Cost", "cost": "Cost", "next_due_date": "Next Due Date", "next_due_km": "Next Due KM", "notes": "Notes",
    }, ["id", "Date", "Service Type", "Garage", "Labour Cost", "Item Cost", "Cost", "Next Due Date", "Next Due KM", "Notes"])
    for col, default in [("Next Due Date", None), ("Next Due KM", None), ("Notes", ""), ("Labour Cost", 0), ("Item Cost", 0)]:
        if not df.empty:
            df[col] = df[col].fillna(default)
    return df


def save_maintenance_record(bus_number: str, record_date, service_type: str, garage_name: str, labour_cost: float,
                             item_cost: float, notes: str, next_due_date, next_due_km, user_email: str) -> None:
    labour_cost, item_cost = float(labour_cost or 0), float(item_cost or 0)
    total_cost = labour_cost + item_cost
    res = supabase.table("maintenance_records").upsert({
        "bus_number": bus_number, "record_date": str(record_date), "service_type": service_type.strip(),
        "garage_name": (garage_name or "").strip(), "labour_cost": labour_cost, "item_cost": item_cost, "cost": total_cost,
        "notes": (notes or "").strip(), "next_due_date": str(next_due_date) if next_due_date else None,
        "next_due_km": int(next_due_km) if next_due_km else None, "updated_by": user_email,
    }, on_conflict="bus_number,record_date,service_type").execute()
    record_id = res.data[0]["id"] if res.data else None
    if not record_id:
        return

    supabase.table("maintenance_records").update({"next_due_date": None, "next_due_km": None}) \
        .eq("bus_number", bus_number).eq("service_type", service_type.strip()).lt("record_date", str(record_date)).execute()

    if total_cost > 0:
        supabase.table("vehicle_expenses").upsert({
            "bus_number": bus_number, "date": str(record_date), "category": f"Maintenance - {service_type.strip()}",
            "amount": total_cost, "description": f"{(garage_name or '').strip()} {(notes or '').strip()}".strip(),
            "maintenance_ref_id": record_id,
        }, on_conflict="maintenance_ref_id").execute()
    else:
        supabase.table("vehicle_expenses").delete().eq("maintenance_ref_id", record_id).execute()


def delete_maintenance_record(bus_number: str, record_id: str) -> None:
    supabase.table("maintenance_records").delete().eq("id", record_id).eq("bus_number", bus_number).execute()


def get_previous_service_date(bus_number: str, service_type: str, before_date):
    res = supabase.table("maintenance_records").select("record_date").eq("bus_number", bus_number) \
        .eq("service_type", service_type).lt("record_date", str(before_date)).order("record_date", desc=True).limit(1).execute()
    return res.data[0]["record_date"] if res.data else None


def get_km_between(bus_number: str, start_date, end_date) -> int:
    query = supabase.table("vehicle_records").select("actual_km").eq("bus_number", bus_number)
    if start_date: query = query.gt("date", str(start_date))
    if end_date: query = query.lte("date", str(end_date))
    return sum(r["actual_km"] or 0 for r in query.execute().data)


@st.cache_data(ttl=3600, show_spinner=False)
def get_avg_daily_km(bus_number: str, days: int = 30) -> float:
    from datetime import date
    start = date.today() - timedelta(days=days)
    rows = supabase.table("vehicle_records").select("actual_km").eq("bus_number", bus_number).gte("date", str(start)).execute().data or []
    return round(sum(r["actual_km"] or 0 for r in rows) / len(rows), 1) if rows else 0.0


@st.cache_data(ttl=3600, show_spinner=False)
def get_diesel_records_raw(bus_numbers: list) -> list:
    if not bus_numbers:
        return []
    return supabase.table("vehicle_records").select("bus_number, diesel, diesel_km") \
        .in_("bus_number", bus_numbers).gt("diesel", 0).execute().data or []


@st.cache_data(ttl=3600, show_spinner=False)
def get_income_records_raw(bus_numbers: list) -> list:
    if not bus_numbers:
        return []
    return supabase.table("vehicle_records").select("bus_number, income, actual_km") \
        .in_("bus_number", bus_numbers).gt("actual_km", 0).execute().data or []


@st.cache_data(ttl=3600, show_spinner=False)
def get_conductor_income_records_raw(bus_numbers: list) -> list:
    """Conductor income-trend (src/ml/conductor_income_trend.py) aur
    festival-aware conductor ranking (src/ml/festival_aware_income.py) ke
    liye — per-record conductor + date + income + actual_km."""
    if not bus_numbers:
        return []
    return supabase.table("vehicle_records").select("bus_number, date, conductor_name, income, actual_km") \
        .in_("bus_number", bus_numbers).gt("actual_km", 0).order("date").execute().data or []


@st.cache_data(ttl=3600, show_spinner=False)
def get_dated_income_records_raw(bus_numbers: list) -> list:
    """Income forecasting (src/ml/income_forecast.py) aur festival-aware
    baseline (src/ml/festival_aware_income.py) ke liye — per-day bus income."""
    if not bus_numbers:
        return []
    return supabase.table("vehicle_records").select("bus_number, date, income, actual_km") \
        .in_("bus_number", bus_numbers).gt("income", 0).order("date").execute().data or []


@st.cache_data(ttl=3600, show_spinner=False)
def get_dated_diesel_records_raw(bus_numbers: list) -> list:
    if not bus_numbers:
        return []
    return supabase.table("vehicle_records").select("bus_number, date, diesel") \
        .in_("bus_number", bus_numbers).gt("diesel", 0).order("date").execute().data or []
