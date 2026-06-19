import pandas as pd
from src.database.config import supabase


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
            "diesel_km":        0   if on_leave else int(row.get("Diesel KM") or 0),
            "income":           0   if on_leave else int(row.get("Income") or 0),
            "updated_by":       current_email,       # ← kaun ne save kiya
            "updated_by_role":  current_role,        # ← uska role
            "remark":           str(row.get("Remark") or ""),
            "next_period":      bool(row.get("Next", False)),
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
        "diesel_km":      "Diesel KM",
        "income":         "Income",
        "remark":         "Remark",
        "next_period":    "Next",
    })

    if "Status" not in df.columns:
        df["Status"] = "Present"
    if "Remark" not in df.columns:
        df["Remark"] = ""
    if "Next" not in df.columns:
        df["Next"] = False
    if "Diesel KM" not in df.columns:
        df["Diesel KM"] = 0

    return df[["Date", "Status", "Driver Name", "Conductor Name", "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Income", "Remark", "Next"]]


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

def get_salary_check(from_date: str = None, to_date: str = None, bus_numbers: list = None) -> pd.DataFrame:
    query = supabase.table("vehicle_records").select(
        "driver_name, bus_number, date"
    )

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

    # Group by driver + bus
    grouped = df.groupby(
        [df["driver_name"].str.strip().str.lower(), "bus_number"]
    ).agg(
        driver_name=("driver_name", "first"),
        bus_number=("bus_number", "first"),
        duties=("date", "nunique"),
    ).reset_index(drop=True)

    # Get salary — bus_number match karke AND date range ke andar
    sal_query = supabase.table("driver_salary").select("driver_name, salary, bus_number, date")
    if from_date:
        sal_query = sal_query.gte("date", from_date)
    if to_date:
        sal_query = sal_query.lte("date", to_date)
    sal_res = sal_query.execute()
    sal_df  = pd.DataFrame(sal_res.data) if sal_res.data else pd.DataFrame(columns=["driver_name", "salary", "bus_number", "date"])

    if not sal_df.empty:
        sal_df["key"] = sal_df["driver_name"].str.strip().str.lower() + "_" + sal_df["bus_number"].fillna("")
        sal_sum = sal_df.groupby("key")["salary"].sum().reset_index()
        grouped["key"] = grouped["driver_name"].str.strip().str.lower() + "_" + grouped["bus_number"].fillna("")
        grouped = grouped.merge(sal_sum, on="key", how="left")
        grouped["salary"] = grouped["salary"].fillna(0)
    else:
        grouped["salary"] = 0

    grouped = grouped[["driver_name", "bus_number", "duties", "salary"]]
    grouped.columns = ["Driver Name", "Bus Number", "Duties", "Salary Given"]
    grouped.insert(0, "Sr No", range(1, len(grouped) + 1))

    return grouped
