import pandas as pd
from src.database.config import supabase


# ══════════════════════════════════════════════
# VEHICLE RECORDS
# ══════════════════════════════════════════════

def save_vehicle_records(bus_number: str, df: pd.DataFrame) -> None:
    from src.database.auth import get_current_role
    import streamlit as st

    user = st.session_state.get("user")
    current_email = user.email if user else "unknown"
    current_role  = get_current_role()

    rows = []
    for _, row in df.iterrows():
        on_leave = str(row.get("Status", "Present")).strip() == "On Leave"
        rows.append({
            "bus_number":       bus_number,
            "date":             str(row["Date"]),
            "status":           "On Leave" if on_leave else "Present",
            "driver_name":      row["Driver Name"],
            "conductor_name":   row["Conductor Name"],
            "scheduled_km":     row["Scheduled KM"],
            "actual_km":        0 if on_leave else row["Actual KM"],
            "diesel":           0.0 if on_leave else float(row.get("Diesel") or 0),
            "income":           0   if on_leave else int(row.get("Income") or 0),
            "updated_by":       current_email,       # ← kaun ne save kiya
            "updated_by_role":  current_role,        # ← uska role
        })

    edited_dates = df["Date"].astype(str).unique().tolist()
    for d in edited_dates:
        supabase.table("vehicle_records") \
            .delete() \
            .eq("bus_number", bus_number) \
            .eq("date", d) \
            .execute()
    supabase.table("vehicle_records").insert(rows).execute()


def get_vehicle_records(bus_number: str) -> pd.DataFrame:
    res = supabase.table("vehicle_records") \
        .select("*") \
        .eq("bus_number", bus_number) \
        .order("date", desc=True) \
        .execute()

    if not res.data:
        return pd.DataFrame(columns=[
            "Date", "Status", "Driver Name", "Conductor Name",
            "Scheduled KM", "Actual KM", "Diesel", "Income"
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
        "income":         "Income",
    })

    # fallback if status column not yet in DB
    if "Status" not in df.columns:
        df["Status"] = "Present"

    return df[["Date", "Status", "Driver Name", "Conductor Name", "Scheduled KM", "Actual KM", "Diesel", "Income"]]


# ══════════════════════════════════════════════
# DRIVER SALARY
# ══════════════════════════════════════════════

def save_driver_salary(df: pd.DataFrame) -> None:
    records = [
        {
            "driver_name": row["Driver Name"],
            "date":        str(row["Date"]),
            "salary":      float(row["Salary"] or 0),
            "transaction": row["Transaction"] or "",
        }
        for _, row in df.iterrows()
    ]
    supabase.table("driver_salary").insert(records).execute()


def get_driver_salary() -> pd.DataFrame:
    res = supabase.table("driver_salary") \
        .select("*") \
        .order("date", desc=True) \
        .execute()

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
    rename = {
        "Date":        "date",
        "Driver Name": "driver_name",
        "Salary":      "salary",
        "Transaction": "transaction",
    }
    db_updates = {rename.get(k, k): v for k, v in updates.items()}
    supabase.table("driver_salary") \
        .update(db_updates) \
        .eq("id", record_id) \
        .execute()


def delete_driver_salary(record_id: str) -> None:
    supabase.table("driver_salary") \
        .delete() \
        .eq("id", record_id) \
        .execute()


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
    rename = {
        "Date":        "date",
        "Category":    "category",
        "Amount":      "amount",
        "Description": "description",
    }
    db_updates = {rename.get(k, k): v for k, v in updates.items()}
    supabase.table("vehicle_expenses") \
        .update(db_updates) \
        .eq("id", expense_id) \
        .execute()


def delete_vehicle_expense(expense_id: str) -> None:
    supabase.table("vehicle_expenses") \
        .delete() \
        .eq("id", expense_id) \
        .execute()


# ══════════════════════════════════════════════
# SALARY CHECK
# ══════════════════════════════════════════════

def get_salary_check(from_date: str = None, to_date: str = None) -> pd.DataFrame:
    res = supabase.table("salary_check").select("*").execute()

    if not res.data:
        return pd.DataFrame(columns=["Sr No", "Driver Name", "Conductor Name", "Duties", "Salary Given"])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "driver_id":      "Sr No",
        "driver_name":    "Driver Name",
        "conductor_name": "Conductor Name",
        "duties":         "Duties",
        "total_salary":   "Salary Given",
    })
    return df[["Sr No", "Driver Name", "Conductor Name", "Duties", "Salary Given"]]
