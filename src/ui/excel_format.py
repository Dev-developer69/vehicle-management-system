import calendar
import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF

from src.database.db import (
    save_vehicle_records,
    save_driver_salary,
    save_vehicle_expenses,
    get_vehicle_records,
    get_driver_salary,
    get_vehicle_expenses,
    get_salary_check,
    get_scheduled_km,
    update_vehicle_expense,
    delete_vehicle_expense,
    update_driver_salary,
    delete_driver_salary,
)


# ──────────────────────────────────────────────
# HELPER: Editor widget state → DataFrame
# ──────────────────────────────────────────────
def _apply_editor_state(original_df: pd.DataFrame, editor_state: dict) -> pd.DataFrame:
    if not editor_state:
        return original_df.copy()
    df = original_df.copy()
    for row_idx, changes in editor_state.get("edited_rows", {}).items():
        for col, val in changes.items():
            if row_idx < len(df):
                df.at[row_idx, col] = val
    added = editor_state.get("added_rows", [])
    if added:
        new_rows = pd.DataFrame(added)
        for col in df.columns:
            if col not in new_rows.columns:
                new_rows[col] = None
        df = pd.concat([df, new_rows[df.columns]], ignore_index=True)
    deleted = sorted(editor_state.get("deleted_rows", []), reverse=True)
    for row_idx in deleted:
        if row_idx < len(df):
            df = df.drop(index=row_idx).reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# HELPER: Total row builder
# ──────────────────────────────────────────────
def build_total_row(df: pd.DataFrame, numeric_cols: list, label_col: str = "Driver Name"):
    total = {}
    for col in df.columns:
        if col == label_col:
            total[col] = "TOTAL"
        elif col == "Avg":
            valid = pd.to_numeric(df["Avg"], errors="coerce").dropna()
            total[col] = round(float(valid.mean()), 2) if not valid.empty else 0.0
        elif col in numeric_cols:
            total[col] = round(float(pd.to_numeric(df[col], errors="coerce").sum()), 3)
        else:
            total[col] = ""
    return pd.DataFrame({k: [v] for k, v in total.items()})


# ──────────────────────────────────────────────
# HELPER: Generate PDF — Vehicle Records
# ──────────────────────────────────────────────
def _generate_pdf(df, total_row, bus_number, month, half):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, f"Vehicle Records - {bus_number}  |  {month_name} ({half})", ln=True, align="C")
    pdf.ln(3)
    cols = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, str(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 8)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, str(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, str(total_row.iloc[0][col]), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


# ──────────────────────────────────────────────
# HELPER: Generate PDF — Expenses
# ──────────────────────────────────────────────
def _generate_expenses_pdf(df, bus_number, month, period):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, f"Vehicle Expenses - {bus_number}  |  {month_name} ({period})", ln=True, align="C")
    pdf.ln(3)
    cols = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 8, str(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, str(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    total_amount = pd.to_numeric(df["Amount"], errors="coerce").sum()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        val = "TOTAL" if col == "Category" else (f"{total_amount:,.0f}" if col == "Amount" else "")
        pdf.cell(col_w, 8, str(val), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


# ──────────────────────────────────────────────
# HELPER: Date range filter
# ──────────────────────────────────────────────
def _get_date_range(year, month, period):
    if period == "1-15":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    elif period == "16-31":
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 16), pd.Timestamp(year, month, last_day)
    else:
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, last_day)


# ──────────────────────────────────────────────
# HELPER: Previous period range (for "Next" shift logic)
# ──────────────────────────────────────────────
def _shift_period_back(year, month, period):
    """
    Agar current view '16-31' hai → previous period '1-15' same month hai.
    Agar current view '1-15' hai → previous period '16-31' pichle month hai.
    """
    if period == "16-31":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    else:  # period == "1-15" → pichla month ka 16-31
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        last_day   = calendar.monthrange(prev_year, prev_month)[1]
        return pd.Timestamp(prev_year, prev_month, 16), pd.Timestamp(prev_year, prev_month, last_day)


# ──────────────────────────────────────────────
# 1. VEHICLE RECORDS
# ──────────────────────────────────────────────
def editable_grid(bus_number: str):
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Avg", "Income"]
    key          = f"grid_{bus_number}"
    ed_key       = f"editor_{bus_number}"
    fetch_key    = f"fetched_{bus_number}"
    confirm_key  = f"show_confirm_{bus_number}"
    pending_key  = f"pending_df_{bus_number}"
    sched_km_key = f"sched_km_{bus_number}"

    if sched_km_key not in st.session_state:
        st.session_state[sched_km_key] = get_scheduled_km(bus_number)
    scheduled_km = st.session_state[sched_km_key]

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":           [date.today()],
            "Status":         ["Present"],
            "Driver Name":    [None],
            "Conductor Name": [None],
            "Scheduled KM":   [scheduled_km],
            "Actual KM":      [0],
            "Diesel":         [0.00],
            "Diesel KM":      [0],
            "Income":         [0],
            "Remark":         [""],
            "Next":           [False],
        })

    st.markdown(f"### Vehicle Records {bus_number} 🚐")
    st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":           st.column_config.DateColumn("Date", default=date.today()),
            "Status":         st.column_config.SelectboxColumn("Status", options=["Present", "On Leave"], default="Present"),
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Conductor Name": st.column_config.TextColumn("Conductor Name"),
            "Scheduled KM":   st.column_config.NumberColumn("Scheduled KM", min_value=0, default=scheduled_km),
            "Actual KM":      st.column_config.NumberColumn("Actual KM", min_value=0, default=0),
            "Diesel":         st.column_config.NumberColumn("Diesel", min_value=0.0, default=0.0, step=0.01, format="%.2f"),
            "Diesel KM":      st.column_config.NumberColumn("Diesel KM", min_value=0, default=0, help="Itne diesel se itna km chala"),
            "Income":         st.column_config.NumberColumn("Income", min_value=0, default=0),
            "Remark":         st.column_config.TextColumn("Remark"),
            "Next":           st.column_config.CheckboxColumn("Next", default=False, help="Yes = is entry ko next period mein count karo"),
        },
    )

    editor_state  = st.session_state.get(ed_key, {})
    edited_df     = _apply_editor_state(st.session_state[key], editor_state)
    on_leave_mask = edited_df["Status"] == "On Leave"
    edited_df.loc[on_leave_mask, "Scheduled KM"] = 0
    edited_df.loc[on_leave_mask, "Actual KM"]    = 0
    edited_df.loc[on_leave_mask, "Income"]        = 0

    if st.session_state.get(confirm_key):
        st.warning("⚠️ Duplicate dates exist. Wanna update?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Update", key=f"yes_{bus_number}"):
                save_vehicle_records(bus_number, st.session_state.get(pending_key))
                st.success("✅ Updated!")
                for k in [key, fetch_key, confirm_key, pending_key]:
                    st.session_state.pop(k, None)
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key=f"no_{bus_number}"):
                st.session_state.pop(confirm_key, None)
                st.session_state.pop(pending_key, None)
                st.rerun()
    else:
        if st.button("💾 Save Changes", key=f"save_{bus_number}", use_container_width=True):
            cleaned_df = edited_df[
                edited_df["Driver Name"].notna() &
                (edited_df["Driver Name"].astype(str).str.strip() != "")
            ].copy()
            if cleaned_df.empty:
                st.warning("⚠️ No valid rows to save.")
                return
            if fetch_key not in st.session_state:
                st.session_state[fetch_key] = get_vehicle_records(bus_number)
            fetched_df = st.session_state[fetch_key]
            new_dates      = set(cleaned_df["Date"].astype(str).tolist())
            existing_dates = set(fetched_df["Date"].astype(str).tolist()) if not fetched_df.empty else set()
            if new_dates & existing_dates:
                st.session_state[pending_key] = cleaned_df
                st.session_state[confirm_key] = True
                st.rerun()
            else:
                save_vehicle_records(bus_number, cleaned_df)
                st.success("✅ Saved!")
                st.session_state.pop(key, None)
                st.session_state.pop(fetch_key, None)
                st.rerun()

    st.markdown("### Saved Records 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_records(bus_number)
    fetched_df = st.session_state[fetch_key]

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                             format_func=lambda x: date(2000, x, 1).strftime("%B"), key=f"month_{bus_number}")
    with col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        half = st.radio("Period", ["1-15", "16-31"], index=0 if default_half == "1-15" else 1,
                        horizontal=True, key=f"half_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key=f"refresh_{bus_number}", use_container_width=True):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        display_df = fetched_df.copy()
        display_df["Date"] = pd.to_datetime(display_df["Date"])
        if "Next" not in display_df.columns:
            display_df["Next"] = False

        start, end = _get_date_range(date.today().year, month, half)

        # Normal rows jo is period mein aate hain (Next == False)
        normal_mask = (display_df["Date"] >= start) & (display_df["Date"] <= end) & (display_df["Next"] == False)

        # Next == True rows jiska actual date PREVIOUS period mein hai, lekin shift karke yahan aane chahiye
        prev_start, prev_end = _shift_period_back(date.today().year, month, half)
        shifted_mask = (display_df["Date"] >= prev_start) & (display_df["Date"] <= prev_end) & (display_df["Next"] == True)

        display_df = display_df[normal_mask | shifted_mask]
        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        if "Diesel KM" not in display_df.columns:
            display_df["Diesel KM"] = 0
        display_df["Avg"]  = (
            pd.to_numeric(display_df["Diesel KM"], errors="coerce") /
            pd.to_numeric(display_df["Diesel"], errors="coerce").replace(0, float("nan"))
        ).round(2)
        if "Income" not in display_df.columns: display_df["Income"] = 0
        if "Remark" not in display_df.columns: display_df["Remark"] = ""
        display_df = display_df[["Date", "Status", "Driver Name", "Conductor Name",
                                  "Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Avg", "Income", "Remark", "Next"]]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        total_row = build_total_row(display_df, numeric_cols, label_col="Driver Name")
        st.dataframe(total_row, use_container_width=True, hide_index=True)
        pdf_bytes = _generate_pdf(display_df, total_row, bus_number, month, half)
        st.download_button("📥 Download PDF", data=pdf_bytes,
                           file_name=f"vehicle_records_{bus_number}_{date(2000,month,1).strftime('%B')}_{half.replace('-','_')}.pdf",
                           mime="application/pdf", key=f"pdf_{bus_number}")
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 2. DRIVER SALARY  ← bus_number se filter
# ──────────────────────────────────────────────
def driver_salary(bus_number: str = ""):
    key       = f"driver_salary_{bus_number}"
    ed_key    = f"editor_salary_{bus_number}"
    fetch_key = f"fetched_salary_{bus_number}"

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":        [date.today()],
            "Driver Name": [None],
            "Salary":      [0],
            "Transaction": [""],
        })

    st.markdown("### Driver Salary 💰")
    st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":        st.column_config.DateColumn("Date", default=date.today()),
            "Driver Name": st.column_config.TextColumn("Driver Name"),
            "Salary":      st.column_config.NumberColumn("Salary", min_value=0, default=0),
            "Transaction": st.column_config.TextColumn("Transaction"),
        },
    )

    editor_state = st.session_state.get(ed_key, {})
    edited_df    = _apply_editor_state(st.session_state[key], editor_state)

    if st.button("💾 Save Changes", key=f"save_salary_{bus_number}"):
        cleaned_df = edited_df[
            edited_df["Driver Name"].notna() &
            (edited_df["Driver Name"].astype(str).str.strip() != "")
        ].copy()
        if cleaned_df.empty:
            st.warning("⚠️ No valid rows to save.")
            return
        # ← bus_number pass karo
        save_driver_salary(cleaned_df, bus_number=bus_number)
        st.success("✅ Saved!")
        st.session_state.pop(key, None)
        st.session_state.pop(fetch_key, None)
        st.rerun()

    st.markdown("### Saved Salary Records 📋")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        sal_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                                 format_func=lambda x: date(2000, x, 1).strftime("%B"),
                                 key=f"sal_month_{bus_number}")
    with col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        sal_half = st.radio("Period", ["1-15", "16-31"], index=0 if default_half == "1-15" else 1,
                            horizontal=True, key=f"sal_half_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key=f"ref_sal_{bus_number}", use_container_width=True):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if fetch_key not in st.session_state:
        # ← bus_number se filter karke fetch karo
        st.session_state[fetch_key] = get_driver_salary(bus_number=bus_number)
    fetched_df = st.session_state[fetch_key]

    if not fetched_df.empty:
        # Date filter
        disp = fetched_df.copy()
        disp["Date"] = pd.to_datetime(disp["Date"])
        start, end = _get_date_range(date.today().year, sal_month, sal_half)
        disp = disp[(disp["Date"] >= start) & (disp["Date"] <= end)].copy()
        disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")

        st.data_editor(
            disp,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"edit_sal_{bus_number}",
            column_config={
                "id":          None,
                "Date":        st.column_config.TextColumn("Date"),
                "Driver Name": st.column_config.TextColumn("Driver Name"),
                "Salary":      st.column_config.NumberColumn("Salary", min_value=0),
                "Transaction": st.column_config.TextColumn("Transaction"),
            }
        )

        if st.button("💾 Update Salary", key=f"update_sal_{bus_number}"):
            sal_editor_state = st.session_state.get(f"edit_sal_{bus_number}", {})
            for row_idx, changes in sal_editor_state.get("edited_rows", {}).items():
                update_driver_salary(disp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(sal_editor_state.get("deleted_rows", []), reverse=True):
                delete_driver_salary(disp.iloc[row_idx]["id"])
            st.success("✅ Updated!")
            st.session_state.pop(fetch_key, None)
            st.rerun()

        total_row = build_total_row(disp, ["Salary"], label_col="Driver Name")
        st.dataframe(total_row, use_container_width=True, hide_index=True)
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 3. VEHICLE EXPENSES
# ──────────────────────────────────────────────
def expenses(bus_number: str = ""):
    key       = f"expenses_{bus_number}"
    ed_key    = f"editor_expenses_{bus_number}"
    fetch_key = f"fetched_expenses_{bus_number}"

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":        [date.today()],
            "Category":    [""],
            "Amount":      [0],
            "Description": [""],
        })

    st.markdown("### Vehicle Expenses 🧾")
    st.data_editor(
        st.session_state[key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":        st.column_config.DateColumn("Date", default=date.today()),
            "Category":    st.column_config.TextColumn("Category"),
            "Amount":      st.column_config.NumberColumn("Amount", min_value=0, default=0),
            "Description": st.column_config.TextColumn("Description"),
        },
    )

    editor_state = st.session_state.get(ed_key, {})
    edited_df    = _apply_editor_state(st.session_state[key], editor_state)

    if st.button("💾 Save Changes", key=f"save_expenses_{bus_number}"):
        cleaned_df = edited_df[
            edited_df["Category"].notna() &
            (edited_df["Category"].str.strip() != "")
        ].copy()
        if cleaned_df.empty:
            st.warning("⚠️ No valid rows to save.")
            return
        save_vehicle_expenses(bus_number, cleaned_df)
        st.success("✅ Saved!")
        st.session_state.pop(key, None)
        st.session_state.pop(fetch_key, None)
        st.rerun()

    st.markdown("### Saved Expenses 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_expenses(bus_number)
    fetched_df = st.session_state[fetch_key]

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        exp_month = st.selectbox("Month", options=list(range(1, 13)), index=date.today().month - 1,
                                 format_func=lambda x: date(2000, x, 1).strftime("%B"),
                                 key=f"exp_month_{bus_number}")
    with col2:
        exp_period = st.radio("Period", ["1-15", "16-31", "01-31"], index=2,
                              horizontal=True, key=f"exp_period_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", key=f"ref_exp_{bus_number}", use_container_width=True):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        display_exp = fetched_df.copy()
        display_exp["Date"] = pd.to_datetime(display_exp["Date"])
        start, end = _get_date_range(date.today().year, exp_month, exp_period)
        display_exp = display_exp[(display_exp["Date"] >= start) & (display_exp["Date"] <= end)].copy()
        display_exp["Date"] = display_exp["Date"].dt.strftime("%Y-%m-%d")

        st.data_editor(
            display_exp, use_container_width=True, hide_index=True, num_rows="dynamic",
            key=f"edit_exp_{bus_number}",
            column_config={
                "id":          None,
                "Date":        st.column_config.TextColumn("Date"),
                "Category":    st.column_config.TextColumn("Category"),
                "Amount":      st.column_config.NumberColumn("Amount", min_value=0),
                "Description": st.column_config.TextColumn("Description"),
            }
        )

        if st.button("💾 Update Expenses", key=f"update_exp_{bus_number}"):
            exp_editor_state = st.session_state.get(f"edit_exp_{bus_number}", {})
            for row_idx, changes in exp_editor_state.get("edited_rows", {}).items():
                update_vehicle_expense(display_exp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(exp_editor_state.get("deleted_rows", []), reverse=True):
                delete_vehicle_expense(display_exp.iloc[row_idx]["id"])
            st.success("✅ Updated!")
            st.session_state.pop(fetch_key, None)
            st.rerun()

        total_amount = pd.to_numeric(display_exp["Amount"], errors="coerce").sum()
        st.markdown(f"""
        <div style='background:#2D2D5E;border-radius:8px;padding:12px 20px;margin-top:8px;'>
            <span style='color:#aaa;'>Total: </span>
            <span style='color:#7B8CFF;font-size:1.2rem;font-weight:bold;'>₹{total_amount:,.0f}</span>
        </div>""", unsafe_allow_html=True)

        pdf_data = _generate_expenses_pdf(
            display_exp[["Date", "Category", "Amount", "Description"]],
            bus_number, exp_month, exp_period
        )
        st.download_button("📥 Download PDF", data=pdf_data,
                           file_name=f"expenses_{bus_number}_{date(2000,exp_month,1).strftime('%B')}_{exp_period.replace('-','_')}.pdf",
                           mime="application/pdf", key=f"exp_pdf_{bus_number}")
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 4. SALARY CHECK
# ──────────────────────────────────────────────
def salary_check_view():
    st.markdown("### Salary Check 📊")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        from_date = st.date_input("From", value=None, key="sc_from", format="YYYY-MM-DD")
    with col2:
        to_date = st.date_input("To", value=None, key="sc_to", format="YYYY-MM-DD")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key="sc_load"):
            st.session_state["salary_check_df"] = get_salary_check(
                from_date=str(from_date) if from_date else None,
                to_date=str(to_date) if to_date else None,
            )
    if "salary_check_df" in st.session_state:
        df = st.session_state["salary_check_df"]
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No data found.")
