import pandas as pd
from src.database.config import supabase, supabase_admin


# ══════════════════════════════════════════════
# VEHICLE RECORDS
# ══════════════════════════════════════════════

def get_scheduled_km(bus_number: str) -> int:
    res = supabase.table("vehicle_scheduled_km") \
        .select("scheduled_km") \
        .eq("bus_number", bus_number) \
        .execute()
    if res.data:
        return int(res.data[0]["scheduled_km"] or 466)
    return 466


# saved data mai se kisi row ko dlt krne ka function
def delete_vehicle_record(bus_number: str, date_str: str) -> None:
    supabase.table("vehicle_records") \
        .delete() \
        .eq("bus_number", bus_number) \
        .eq("date", date_str) \
        .execute()


def _safe_int(val):
    """None/NaN/empty-safe int conversion."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if isinstance(val, str) and val.strip() == "":
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None

def save_vehicle_records(bus_number: str, df: pd.DataFrame) -> None:
    from src.database.auth import get_current_role
    import streamlit as st

    user          = st.session_state.get("user")
    current_email = user.email if user else "unknown"
    current_role  = get_current_role()

    for _, row in df.iterrows():
        date_str = str(row["Date"])
        on_leave = str(row.get("Status", "Present")).strip() == "On Leave"

        # Pehle existing record fetch karo
        existing = supabase.table("vehicle_records") \
            .select("*") \
            .eq("bus_number", bus_number) \
            .eq("date", date_str) \
            .execute()

        new_data = {
            "bus_number":      bus_number,
            "date":            date_str,
            "status":          "On Leave" if on_leave else "Present",
            "driver_name":     row.get("Driver Name"),
            "conductor_name":  row.get("Conductor Name"),
            "scheduled_km":    0 if on_leave else row.get("Scheduled KM", 0),
            "actual_km":       0 if on_leave else row.get("Actual KM", 0),
            "diesel": None if on_leave else (float(row.get("Diesel")) if pd.notna(row.get("Diesel")) else None),
            "diesel_km": None if on_leave else _safe_int(row.get("Diesel KM")),
            "income":    None if on_leave else _safe_int(row.get("Income")),
            "updated_by":      current_email,
            "updated_by_role": current_role,
            "remark":          str(row.get("Remark") or ""),
            "next_period":     bool(row.get("Next", False)),
        }

        if existing.data:
            # Record exist karta hai — sirf filled values update karo, baki purani rakho
            old = existing.data[0]

            def keep(new_val, old_val, empty_vals):
                return new_val if new_val not in empty_vals else old_val

            merged = {
                "bus_number":      bus_number,
                "date":            date_str,
                "status":          new_data["status"],
                "updated_by":      current_email,
                "updated_by_role": current_role,
                "remark":          new_data["remark"] or old.get("remark", ""),
                "next_period":     new_data["next_period"],
                "driver_name":     keep(new_data["driver_name"],    old.get("driver_name"),    [None, "", "None"]),
                "conductor_name":  keep(new_data["conductor_name"], old.get("conductor_name"), [None, "", "None"]),
                "scheduled_km":    new_data["scheduled_km"],  
                "actual_km":       new_data["actual_km"],   
                "diesel":          keep(new_data["diesel"],         old.get("diesel"),          [None]),
                "diesel_km":       keep(new_data["diesel_km"],      old.get("diesel_km"),       [None]),
                "income":          keep(new_data["income"],         old.get("income"),          [None]),
            }
            supabase.table("vehicle_records") \
                .update(merged) \
                .eq("bus_number", bus_number) \
                .eq("date", date_str) \
                .execute()
        else:
            # Naya record — direct insert
            supabase.table("vehicle_records").insert(new_data).execute()


def get_vehicle_records(bus_number: str) -> pd.DataFrame:
    res = supabase.table("vehicle_records") \
        .select("*") \
        .eq("bus_number", bus_number) \
        .order("date", desc=True) \
        .execute()

    if not res.data:
        return pd.DataFrame(columns=[
            "Date", "Status", "Driver Name", "Conductor Name",
            "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Income", "Remark", "Next"
        ])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "date":           "Date",
        "status":         "Status",
        "driver_name":    "Driver Name",
        "conductor_name": "Conductor Name",
        "scheduled_km":   "Scheduled KM",
        "actual_km":      "Actual KM",
        "diesel":         "Diesel",
        "diesel_km":      "Diesel KM",
        "income":         "Income",
        "remark":         "Remark",
        "next_period":    "Next",
    })

    for col, default in [("Status", "Present"), ("Remark", ""), ("Next", False), ("Diesel KM", 0)]:
        if col not in df.columns:
            df[col] = default

    return df[["Date", "Status", "Driver Name", "Conductor Name",
               "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Income", "Remark", "Next"]]


def get_diesel_summary(bus_number: str, from_date: str, to_date: str) -> pd.DataFrame:
    res = supabase.table("vehicle_records") \
        .select("date, diesel, status") \
        .eq("bus_number", bus_number) \
        .gte("date", from_date) \
        .lte("date", to_date) \
        .order("date", desc=False) \
        .execute()

    if not res.data:
        return pd.DataFrame(columns=["Date", "Diesel"])

    df = pd.DataFrame(res.data)
    df = df[df["status"] != "On Leave"]
    df = df.rename(columns={"date": "Date", "diesel": "Diesel"})
    df["Diesel"] = pd.to_numeric(df["Diesel"], errors="coerce").fillna(0)
    return df[["Date", "Diesel"]]


# ══════════════════════════════════════════════
# DIESEL RATE + PAYMENT (universal — per bus, month, period)
# ══════════════════════════════════════════════

def get_diesel_rate_payment(bus_number: str, month: int, period: str) -> dict:
    res = supabase_admin.table("diesel_details") \
        .select("rate, paid_amount, payment_done") \
        .eq("bus_number", bus_number) \
        .eq("month", month) \
        .eq("period", period) \
        .execute()
    if res.data:
        return {
            "rate":         float(res.data[0]["rate"] or 90.0),
            "paid_amount":  float(res.data[0]["paid_amount"] or 0),
            "payment_done": bool(res.data[0]["payment_done"]),
        }
    return {"rate": 90.00, "paid_amount": 0.0, "payment_done": False}


def save_diesel_rate_payment(bus_number: str, month: int, period: str,
                              rate: float, paid_amount: float, payment_done: bool) -> None:
    supabase_admin.table("diesel_details").upsert({
        "bus_number":   bus_number,
        "month":        month,
        "period":       period,
        "rate":         rate,
        "paid_amount":  paid_amount,
        "payment_done": payment_done,
    }, on_conflict="bus_number,month,period").execute()


# ══════════════════════════════════════════════
# DIESEL PER-ROW RATE (per date override)
# ══════════════════════════════════════════════

def get_diesel_row_rates(bus_number: str, dates: list) -> dict:
    """{date_str: rate} map fetch karo"""
    if not dates:
        return {}
    res = supabase_admin.table("diesel_row_rates") \
        .select("date, rate") \
        .eq("bus_number", bus_number) \
        .in_("date", dates) \
        .execute()
    return {row["date"]: float(row["rate"]) for row in res.data} if res.data else {}


def save_diesel_row_rate(bus_number: str, row_date: str, rate: float) -> None:
    supabase_admin.table("diesel_row_rates").upsert({
        "bus_number": bus_number,
        "date":       row_date,
        "rate":       rate,
    }, on_conflict="bus_number,date").execute()


# ══════════════════════════════════════════════
# DRIVER SALARY
# ══════════════════════════════════════════════

def save_driver_salary(df: pd.DataFrame, bus_number: str = "") -> None:
    records = [
        {
            "driver_name": row["Driver Name"],
            "date":        str(row["Date"]),
            "salary":      float(row["Salary"] or 0),
            "transaction": row["Transaction"] or "",
            "bus_number":  bus_number,
        }
        for _, row in df.iterrows()
    ]
    supabase.table("driver_salary").insert(records).execute()


def get_driver_salary(bus_number: str = "") -> pd.DataFrame:
    query = supabase.table("driver_salary").select("*").order("date", desc=True)
    if bus_number:
        query = query.eq("bus_number", bus_number)
    res = query.execute()

    if not res.data:
        return pd.DataFrame(columns=["id", "Date", "Driver Name", "Salary", "Transaction"])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "date":        "Date",
        "driver_name": "Driver Name",
        "salary":      "Salary",
        "transaction": "Transaction",
    })
    return df[["id", "Date", "Driver Name", "Salary", "Transaction"]]


def update_driver_salary(record_id: str, updates: dict) -> None:
    rename = {"Date": "date", "Driver Name": "driver_name",
              "Salary": "salary", "Transaction": "transaction"}
    db_updates = {rename.get(k, k): v for k, v in updates.items()}
    supabase.table("driver_salary").update(db_updates).eq("id", record_id).execute()


def delete_driver_salary(record_id: str) -> None:
    supabase.table("driver_salary").delete().eq("id", record_id).execute()


# ══════════════════════════════════════════════
# VEHICLE EXPENSES
# ══════════════════════════════════════════════

def save_vehicle_expenses(bus_number: str, df: pd.DataFrame) -> None:
    records = [
        {
            "bus_number":  bus_number,
            "date":        str(row["Date"]),
            "category":    row["Category"].strip(),
            "amount":      float(row["Amount"] or 0),
            "description": row["Description"] or "",
        }
        for _, row in df.iterrows()
    ]
    supabase.table("vehicle_expenses").insert(records).execute()


def get_vehicle_expenses(bus_number: str) -> pd.DataFrame:
    res = supabase.table("vehicle_expenses") \
        .select("*") \
        .eq("bus_number", bus_number) \
        .order("date", desc=True) \
        .execute()

    if not res.data:
        return pd.DataFrame(columns=["id", "Date", "Category", "Amount", "Description"])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "date":        "Date",
        "category":    "Category",
        "amount":      "Amount",
        "description": "Description",
    })
    return df[["id", "Date", "Category", "Amount", "Description"]]


def update_vehicle_expense(expense_id: str, updates: dict) -> None:
    rename = {"Date": "date", "Category": "category",
              "Amount": "amount", "Description": "description"}
    db_updates = {rename.get(k, k): v for k, v in updates.items()}
    supabase.table("vehicle_expenses").update(db_updates).eq("id", expense_id).execute()


def delete_vehicle_expense(expense_id: str) -> None:
    supabase.table("vehicle_expenses").delete().eq("id", expense_id).execute()


# ══════════════════════════════════════════════
# SALARY CHECK
# ══════════════════════════════════════════════

def get_salary_check(from_date: str = None, to_date: str = None, bus_numbers: list = None) -> pd.DataFrame:
    query = supabase.table("vehicle_records").select("driver_name, bus_number, date")
    if from_date:
        query = query.gte("date", from_date)
    if to_date:
        query = query.lte("date", to_date)
    if bus_numbers:
        query = query.in_("bus_number", bus_numbers)
    res = query.execute()

    if not res.data:
        return pd.DataFrame(columns=["Sr No", "Driver Name", "Bus Number", "Duties", "Salary Given"])

    df = pd.DataFrame(res.data)
    df = df[df["driver_name"].notna()]
    df = df[~df["driver_name"].str.strip().str.lower().isin(["no", "test", "none", ""])]

    grouped = df.groupby(
        [df["driver_name"].str.strip().str.lower(), "bus_number"]
    ).agg(
        driver_name=("driver_name", "first"),
        bus_number=("bus_number", "first"),
        duties=("date", "nunique"),
    ).reset_index(drop=True)

    sal_query = supabase.table("driver_salary").select("driver_name, salary, bus_number, date")
    if from_date:
        sal_query = sal_query.gte("date", from_date)
    if to_date:
        sal_query = sal_query.lte("date", to_date)
    sal_res = sal_query.execute()
    sal_df  = pd.DataFrame(sal_res.data) if sal_res.data else pd.DataFrame(
        columns=["driver_name", "salary", "bus_number", "date"])

    if not sal_df.empty:
        sal_df["key"]  = sal_df["driver_name"].str.strip().str.lower() + "_" + sal_df["bus_number"].fillna("")
        sal_sum        = sal_df.groupby("key")["salary"].sum().reset_index()
        grouped["key"] = grouped["driver_name"].str.strip().str.lower() + "_" + grouped["bus_number"].fillna("")
        grouped        = grouped.merge(sal_sum, on="key", how="left")
        grouped["salary"] = grouped["salary"].fillna(0)
    else:
        grouped["salary"] = 0

    grouped = grouped[["driver_name", "bus_number", "duties", "salary"]]
    grouped.columns = ["Driver Name", "Bus Number", "Duties", "Salary Given"]
    grouped.insert(0, "Sr No", range(1, len(grouped) + 1))
    return grouped
