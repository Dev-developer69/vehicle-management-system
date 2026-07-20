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
            "gross_income": None if on_leave else _safe_int(row.get("Gross Income")),
            "updated_by":      current_email,
            "updated_by_role": current_role,
            "remark":          str(row.get("Remark") or ""),
            "next_period":     bool(row.get("Next", False)),
        }

        if existing.data:
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
                "driver_name":     keep(new_data["driver_name"],    old.get("driver_name"),    [None, "", "None","none"]),
                "conductor_name":  keep(new_data["conductor_name"], old.get("conductor_name"), [None, "", "None","none"]),
                "scheduled_km":    new_data["scheduled_km"],
                "actual_km":       new_data["actual_km"],
                "diesel":          keep(new_data["diesel"],         old.get("diesel"),          [None]),
                "diesel_km":       keep(new_data["diesel_km"],      old.get("diesel_km"),       [None]),
                "income":          keep(new_data["income"],         old.get("income"),          [None]),
                "gross_income":    keep(new_data["gross_income"],   old.get("gross_income"),    [None]),
            }
            supabase.table("vehicle_records") \
                .update(merged) \
                .eq("bus_number", bus_number) \
                .eq("date", date_str) \
                .execute()
        else:
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
            "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Income", "Gross Income", "Remark", "Next"
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
        "gross_income":   "Gross Income",
        "remark":         "Remark",
        "next_period":    "Next",
    })

    for col, default in [("Status", "Present"), ("Remark", ""), ("Next", False), ("Diesel KM", 0), ("Gross Income", 0)]:
        if col not in df.columns:
            df[col] = default

    return df[["Date", "Status", "Driver Name", "Conductor Name",
               "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Income", "Gross Income", "Remark", "Next"]]]


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
            "rate":         float(res.data[0]["rate"] or 95.69),
            "paid_amount":  float(res.data[0]["paid_amount"] or 0),
            "payment_done": bool(res.data[0]["payment_done"]),
        }
    return {"rate": 95.69, "paid_amount": 0.0, "payment_done": False}


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
    import streamlit as st
    from datetime import datetime, timezone
    user = st.session_state.get("user")
    updated_by = user.email if user else "unknown"

    records = []
    for _, row in df.iterrows():
        try:
            salary_val = float(str(row["Salary"]).replace(",", "").strip() or 0)
        except (ValueError, TypeError):
            salary_val = 0.0

        txn_val = str(row.get("Transaction") or "").strip().lower()
        if txn_val not in ("cash", "online"):
            txn_val = "cash"

        records.append({
            "driver_name": str(row["Driver Name"]).strip(),
            "date":        str(row["Date"]),
            "salary":      salary_val,
            "transaction": txn_val,
            "bus_number":  bus_number,
            "updated_by":  updated_by,
            "updated_at":  datetime.now(timezone.utc).isoformat(),
        })

    if not records:
        return

    try:
        supabase.table("driver_salary").insert(records).execute()
    except Exception as e:
        log_error("save_driver_salary", str(e), bus_number=bus_number, extra_data=str(records))
        import streamlit as st
        st.error("⚠️ Save failed — error logged.")


def get_driver_salary(bus_number: str = "") -> pd.DataFrame:
    query = supabase.table("driver_salary").select("*").order("date", desc=True)
    if bus_number:
        query = query.eq("bus_number", bus_number)
    res = query.execute()

    if not res.data:
        return pd.DataFrame(columns=["id", "Date", "Driver Name", "Salary", "Transaction", "Updated By"])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "date":        "Date",
        "driver_name": "Driver Name",
        "salary":      "Salary",
        "transaction": "Transaction",
        "updated_by":  "Updated By",
    })
    df["Updated By"] = df["Updated By"].fillna("")
    return df[["id", "Date", "Driver Name", "Salary", "Transaction", "Updated By"]]


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
    if bus_numbers:
        sal_query = sal_query.in_("bus_number", bus_numbers)  # ✅ FIX: ye line add ki
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


def log_error(function_name: str, error_message: str, bus_number: str = "", extra_data: str = "") -> None:
    try:
        supabase_admin.table("error_logs").insert({
            "function_name": function_name,
            "bus_number":    bus_number,
            "error_message": str(error_message),
            "extra_data":    extra_data,
        }).execute()
    except Exception:
        pass  # logging fail ho jaye to bhi app crash na ho


# ══════════════════════════════════════════════
# SUPPLIERS
# ══════════════════════════════════════════════

def get_suppliers() -> pd.DataFrame:
    res = supabase_admin.table("suppliers").select("*").order("name").execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "Name", "Phone", "Address", "Remark"])
    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "name": "Name", "phone": "Phone",
        "address": "Address", "remark": "Remark"
    })
    df["Remark"] = df["Remark"].fillna("")
    return df[["id", "Name", "Phone", "Address", "Remark"]]


def save_supplier(name: str, phone: str, address: str, remark: str = "") -> tuple:
    name  = name.strip()
    phone = phone.strip() if phone else ""
    if not phone:
        return False, "no_phone"
    existing = supabase_admin.table("suppliers").select("id").ilike("name", name).execute()
    if existing.data:
        return False, "duplicate"
    supabase_admin.table("suppliers").insert({
        "name":    name,
        "phone":   phone,
        "address": address.strip() if address else "",
        "remark":  remark.strip() if remark else "",
    }).execute()
    return True, ""

def delete_supplier(supplier_id: str) -> None:
    supabase_admin.table("suppliers").delete().eq("id", supplier_id).execute()


def get_supplier_products(supplier_id: str) -> pd.DataFrame:
    res = supabase_admin.table("products").select("*") \
        .eq("supplier_id", supplier_id).order("purchased_date", desc=True).execute()
    if not res.data:
        return pd.DataFrame(columns=["Name", "Latest Price", "Old Price", "MRP", "Purchased Date"])
    df = pd.DataFrame(res.data)
    return df.rename(columns={
        "name": "Name", "mrp": "MRP",
        "latest_price": "Latest Price", "old_price": "Old Price",
        "purchased_date": "Purchased Date",
    })[["Name", "Latest Price", "Old Price", "MRP", "Purchased Date"]]


# ══════════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════════

def get_products(search: str = "") -> pd.DataFrame:
    res = supabase_admin.table("products").select("*, suppliers(name)").order("name").execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "Name", "MRP", "Latest Price", "Old Price",
                                      "Quantity", "Remark", "Supplier", "Purchased Date"])
    df = pd.DataFrame(res.data)
    df["Supplier"] = df["suppliers"].apply(lambda x: x["name"] if isinstance(x, dict) else "")
    df = df.rename(columns={
        "name": "Name", "mrp": "MRP",
        "latest_price": "Latest Price", "old_price": "Old Price",
        "purchased_date": "Purchased Date",
        "quantity": "Quantity", "remark": "Remark",
    })
    df["Quantity"] = df["Quantity"].fillna("")
    df["Remark"]   = df["Remark"].fillna("")
    if search:
        df = df[df["Name"].str.lower().str.contains(search.lower(), na=False)]
    return df[["id", "Name", "MRP", "Latest Price", "Old Price",
               "Quantity", "Remark", "Supplier", "Purchased Date"]]


def save_product(name: str, latest_price: float, mrp: float,
                 supplier_id: str, purchased_date: str,
                 quantity: str = "", remark: str = "") -> None:
    name = name.strip()
    existing = supabase_admin.table("products").select("*").eq("name", name).execute()
    if existing.data:
        old = existing.data[0]
        supabase_admin.table("products").update({
            "old_price":      old.get("latest_price"),
            "latest_price":   latest_price,
            "mrp":            mrp if mrp else old.get("mrp"),
            "supplier_id":    supplier_id if supplier_id else old.get("supplier_id"),
            "purchased_date": purchased_date,
            "quantity":       quantity or old.get("quantity", ""),
            "remark":         remark or old.get("remark", ""),
        }).eq("name", name).execute()
    else:
        supabase_admin.table("products").insert({
            "name":           name,
            "mrp":            mrp,
            "latest_price":   latest_price,
            "old_price":      None,
            "supplier_id":    supplier_id if supplier_id else None,
            "purchased_date": purchased_date,
            "quantity":       quantity,
            "remark":         remark,
        }).execute()

def delete_product(product_id: str) -> None:
    supabase_admin.table("products").delete().eq("id", product_id).execute()


# ══════════════════════════════════════════════
# REQUIREMENTS
# ══════════════════════════════════════════════

def get_requirements() -> pd.DataFrame:
    from datetime import datetime, timedelta
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    supabase_admin.table("product_requirements") \
        .delete().eq("fulfilled", True).lt("created_at", week_ago).execute()

    res = supabase_admin.table("product_requirements") \
        .select("*").order("created_at", desc=True).execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "Product Name", "Quantity", "Remark", "Fulfilled", "Created"])
    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "product_name": "Product Name", "quantity": "Quantity",
        "remark": "Remark", "fulfilled": "Fulfilled", "created_at": "Created",
    })
    df["Created"] = pd.to_datetime(df["Created"]).dt.strftime("%Y-%m-%d")
    return df[["id", "Product Name", "Quantity", "Remark", "Fulfilled", "Created"]]


def save_requirement(product_name: str, quantity: str, remark: str) -> None:
    supabase_admin.table("product_requirements").insert({
        "product_name": product_name.strip(),
        "quantity":     quantity.strip(),
        "remark":       remark.strip(),
        "fulfilled":    False,
    }).execute()


def fulfill_requirement(req_id: str, product_name: str,
                         latest_price: float, mrp: float,
                         supplier_id: str, purchased_date: str) -> None:
    save_product(product_name, latest_price, mrp, supplier_id, purchased_date)
    supabase_admin.table("product_requirements") \
        .update({"fulfilled": True}).eq("id", req_id).execute()


def delete_requirement(req_id: str) -> None:
    supabase_admin.table("product_requirements").delete().eq("id", req_id).execute()




# ══════════════════════════════════════════════
# MAINTENANCE RECORDS
# ══════════════════════════════════════════════

def get_maintenance_records(bus_number: str) -> pd.DataFrame:
    res = supabase.table("maintenance_records") \
        .select("*") \
        .eq("bus_number", bus_number) \
        .order("record_date", desc=True) \
        .execute()

    if not res.data:
        return pd.DataFrame(columns=[
            "id", "Date", "Service Type", "Garage", "Labour Cost", "Item Cost", "Cost",
            "Next Due Date", "Next Due KM", "Notes"
        ])

    df = pd.DataFrame(res.data)
    df = df.rename(columns={
        "record_date":   "Date",
        "service_type":  "Service Type",
        "garage_name":   "Garage",
        "labour_cost":   "Labour Cost",
        "item_cost":     "Item Cost",
        "cost":          "Cost",
        "next_due_date": "Next Due Date",
        "next_due_km":   "Next Due KM",
        "notes":         "Notes",
    })
    for col, default in [("Next Due Date", None), ("Next Due KM", None), ("Notes", ""),
                          ("Labour Cost", 0), ("Item Cost", 0)]:
        if col not in df.columns:
            df[col] = default

    return df[["id", "Date", "Service Type", "Garage", "Labour Cost", "Item Cost", "Cost",
               "Next Due Date", "Next Due KM", "Notes"]]


def save_maintenance_record(bus_number: str, record_date, service_type: str,
                             garage_name: str, labour_cost: float, item_cost: float, notes: str,
                             next_due_date, next_due_km, user_email: str) -> None:
    labour_cost = float(labour_cost or 0)
    item_cost   = float(item_cost or 0)
    total_cost  = labour_cost + item_cost

    res = supabase.table("maintenance_records").upsert({
        "bus_number":     bus_number,
        "record_date":    str(record_date),
        "service_type":   service_type.strip(),
        "garage_name":    (garage_name or "").strip(),
        "labour_cost":    labour_cost,
        "item_cost":      item_cost,
        "cost":           total_cost,
        "notes":          (notes or "").strip(),
        "next_due_date":  str(next_due_date) if next_due_date else None,
        "next_due_km":    int(next_due_km) if next_due_km else None,
        "updated_by":     user_email,
    }, on_conflict="bus_number,record_date,service_type").execute()
    record_id = res.data[0]["id"] if res.data else None
    if not record_id:
        return

    # ── Stale reminder clear ──
    supabase.table("maintenance_records") \
        .update({"next_due_date": None, "next_due_km": None}) \
        .eq("bus_number", bus_number) \
        .eq("service_type", service_type.strip()) \
        .lt("record_date", str(record_date)) \
        .execute()

    # ── Sync to Vehicle Expenses ──
    if total_cost > 0:
        supabase.table("vehicle_expenses").upsert({
            "bus_number":         bus_number,
            "date":               str(record_date),
            "category":           f"Maintenance - {service_type.strip()}",
            "amount":             total_cost,
            "description":        f"{(garage_name or '').strip()} {(notes or '').strip()}".strip(),
            "maintenance_ref_id": record_id,
        }, on_conflict="maintenance_ref_id").execute()
    else:
        supabase.table("vehicle_expenses").delete().eq("maintenance_ref_id", record_id).execute()


def delete_maintenance_record(bus_number: str, record_id: str) -> None:
    supabase.table("maintenance_records") \
        .delete() \
        .eq("id", record_id) \
        .eq("bus_number", bus_number) \
        .execute()


def get_previous_service_date(bus_number: str, service_type: str, before_date):
    """Same service_type ki turant pichli occurrence (before_date se strictly pehle)"""
    res = supabase.table("maintenance_records") \
        .select("record_date") \
        .eq("bus_number", bus_number) \
        .eq("service_type", service_type) \
        .lt("record_date", str(before_date)) \
        .order("record_date", desc=True) \
        .limit(1) \
        .execute()
    return res.data[0]["record_date"] if res.data else None


def get_km_between(bus_number: str, start_date, end_date) -> int:
    """vehicle_records se Actual KM sum karo, start_date ke baad se end_date tak"""
    query = supabase.table("vehicle_records").select("actual_km").eq("bus_number", bus_number)
    if start_date:
        query = query.gt("date", str(start_date))
    if end_date:
        query = query.lte("date", str(end_date))
    records = query.execute()
    return sum(r["actual_km"] or 0 for r in records.data)
