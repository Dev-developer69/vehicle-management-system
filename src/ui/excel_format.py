import calendar
import streamlit as st
import pandas as pd
from datetime import date
from fpdf import FPDF

from src.screens.products_manager import _extract_data_from_image
from src.database.db import (
    save_vehicle_records, save_driver_salary, save_vehicle_expenses,
    get_vehicle_records, get_driver_salary, get_vehicle_expenses,
    get_salary_check, get_scheduled_km, get_diesel_summary,
    update_vehicle_expense, delete_vehicle_expense,
    update_driver_salary, delete_driver_salary,delete_vehicle_record,
    get_diesel_rate_payment, save_diesel_rate_payment,
    get_diesel_row_rates, save_diesel_row_rate,
    get_suppliers, save_supplier, delete_supplier, get_supplier_products,
    get_products, save_product, delete_product,
    get_requirements, save_requirement, fulfill_requirement, delete_requirement,

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
# HELPER: Previous period shift (for Next flag)
# ──────────────────────────────────────────────
def shift_period_back(year, month, period):
    if period == "16-31":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        last_day   = calendar.monthrange(prev_year, prev_month)[1]
        return pd.Timestamp(prev_year, prev_month, 16), pd.Timestamp(prev_year, prev_month, last_day)


# ──────────────────────────────────────────────
# HELPER: Generate PDF — Vehicle Records
# ──────────────────────────────────────────────
def _safe_pdf_text(val) -> str:
    """FPDF core fonts (Helvetica) sirf Latin-1 support karte hain — unsupported chars replace karo"""
    text = str(val)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _generate_pdf(df, total_row, bus_number, month, half):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, _safe_pdf_text(f"Vehicle Records - {bus_number}  |  {month_name} ({half})"), ln=True, align="C")
    pdf.ln(3)
    cols   = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 8)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, _safe_pdf_text(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 8)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(total_row.iloc[0][col]), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


def _generate_expenses_pdf(df, bus_number, month, period):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Helvetica", "B", 14)
    month_name = date(2000, month, 1).strftime("%B")
    pdf.cell(0, 10, _safe_pdf_text(f"Vehicle Expenses - {bus_number}  |  {month_name} ({period})"), ln=True, align="C")
    pdf.ln(3)
    cols   = list(df.columns)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w  = page_w / len(cols)
    pdf.set_fill_color(52, 73, 94); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 8, _safe_pdf_text(col), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9)
    for i, row in df.iterrows():
        fill = i % 2 == 0
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        for col in cols:
            pdf.cell(col_w, 7, _safe_pdf_text(row[col]) if pd.notna(row[col]) else "", border=1, align="C", fill=fill)
        pdf.ln()
    total_amount = pd.to_numeric(df["Amount"], errors="coerce").sum()
    pdf.set_fill_color(230, 240, 255); pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        val = "TOTAL" if col == "Category" else (f"{total_amount:,.0f}" if col == "Amount" else "")
        pdf.cell(col_w, 8, _safe_pdf_text(val), border=1, align="C", fill=True)
    pdf.ln()
    return bytes(pdf.output())


# ──────────────────────────────────────────────
# 1. VEHICLE RECORDS
# ──────────────────────────────────────────────
def editable_grid(bus_number: str):
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Diesel KM", "Avg", "Income", "Gross Income"]
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
            "Diesel":         [None],
            "Diesel KM":      [None],
            "Income":         [None],
            "Gross Income":   [None],
            "Remark":         [""],
            "Next":           [False],
        })

    st.markdown(f"### Vehicle Records {bus_number} 🚐")

   # ── Extract Income from Image (bulk — poore period ka table, 1 ya 2 images) ──
    with st.expander("📷 Extract Records from Image (optional)"):
        st.caption("Agar sheet chaudi hai aur do photos mein aayi hai (ek mein Date, dusri mein Income/Diesel), dono upload karo — rows same order mein match hongi.")
        img_file_1 = st.file_uploader("Image 1 (Date wali, ya poori image)",
                                       type=["jpg", "jpeg", "png", "webp"],
                                       key=f"inc_img1_{bus_number}")
        img_file_2 = st.file_uploader("Image 2 (optional — baaki columns wali)",
                                       type=["jpg", "jpeg", "png", "webp"],
                                       key=f"inc_img2_{bus_number}")

        if img_file_1 and st.button("🔍 Extract", key=f"inc_extract_{bus_number}"):
            with st.spinner("Extracting..."):
                from src.screens.products_manager import _extract_data_from_images

                images = [(img_file_1.read(), img_file_1.type)]
                if img_file_2:
                    images.append((img_file_2.read(), img_file_2.type))

                prompt = (
                    "This is a vehicle log table with varying column names across different sheets. "
                    + ("Two images are provided — they show the SAME rows in the SAME order, "
                       "just different columns of a wide table split across two photos. "
                       "Merge them row-by-row by position (1st row of image 1 = 1st row of image 2, etc.). "
                       if img_file_2 else "")
                    + "Extract every row (skip the TOTAL/summary row). "
                    "For each row, only extract these fields if a matching column exists "
                    "(match by meaning, column headers may vary):\n"
                    "- date: the row's date (day/date column). Convert to YYYY-MM-DD. "
                    "If only one date is shown for the whole sheet, use it for every row and add day offset if a day-of-month/serial column exists.\n"
                    "- scheduled_km: column like 'Sch', 'Scheduled', 'SCH.KM'\n"
                    "- actual_km: column like 'Actual', 'ACT.KM'\n"
                    "- diesel: column like 'Diesel', 'DSL', 'Fuel' (litres)\n"
                    "- income: column like 'Income', 'INCOME', 'Base Fare' (NOT other-income, NOT per-km, NOT load factor)\n"
                    "- gross_income: column like 'Gross', 'GROSS', 'Total Income'\n\n"
                    "IGNORE all other columns (e.g. IPKM, LF, OTH.INC, load factor, per-km rates, habaa, registration number). "
                    "If a field's matching column is not present in the image(s), set it to null — do not guess. "
                    "Return ONLY a JSON array with keys: date, scheduled_km, actual_km, diesel, income, gross_income. "
                    "No explanation, no markdown, just raw JSON array."
                )

                result = _extract_data_from_images(images, prompt)

            if result:
                rows = []
                for r in result:
                    rows.append({
                        "Date":           pd.to_datetime(r.get("date"), errors="coerce"),
                        "Status":         "Present",
                        "Driver Name":    None,
                        "Conductor Name": None,
                        "Scheduled KM":   r.get("scheduled_km") or 0,
                        "Actual KM":      r.get("actual_km") or 0,
                        "Diesel":         r.get("diesel"),
                        "Diesel KM":      None,
                        "Income":         r.get("income"),
                        "Gross Income":   r.get("gross_income") or 0,
                        "Remark":         "",
                        "Next":           False,
                    })
                new_df = pd.DataFrame(rows)
                new_df = new_df.dropna(subset=["Date"])
                new_df["Date"] = new_df["Date"].dt.date
                st.session_state[key] = new_df
                st.success(f"✅ {len(new_df)} rows extracted — Driver/Conductor Name bhar ke Save karo")
                st.rerun()
            else:
                st.warning("⚠️ Extraction failed, fill manually .")

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
            "Diesel":         st.column_config.NumberColumn("Diesel", min_value=0.0, step=0.01, format="%.2f"),
            "Diesel KM":      st.column_config.NumberColumn("Diesel KM", min_value=0),
            "Income":         st.column_config.NumberColumn("Income", min_value=0),
            "Gross Income":   st.column_config.NumberColumn("Gross Income", min_value=0),
            "Remark":         st.column_config.TextColumn("Remark"),
            "Next":           st.column_config.CheckboxColumn("Next", default=False),
        },
    )

    editor_state  = st.session_state.get(ed_key, {})
    edited_df     = _apply_editor_state(st.session_state[key], editor_state)
    on_leave_mask = edited_df["Status"] == "On Leave"
    edited_df.loc[on_leave_mask, ["Scheduled KM", "Actual KM", "Income"]] = 0

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
            fetched_df     = st.session_state[fetch_key]
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

    # ── Delete row by date ──
    with st.expander("🗑️ Delete a record by date"):
        del_date = st.date_input("Select date to delete", value=date.today(), key=f"del_date_{bus_number}")
        if st.button("Delete this record", key=f"del_btn_{bus_number}"):
            delete_vehicle_record(bus_number, str(del_date))
            st.success(f"✅ Deleted record for {del_date}")
            st.session_state.pop(fetch_key, None)
            st.rerun()

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
        start, end           = _get_date_range(date.today().year, month, half)
        normal_mask          = (display_df["Date"] >= start) & (display_df["Date"] <= end) & (display_df["Next"] == False)
        prev_start, prev_end = shift_period_back(date.today().year, month, half)
        shifted_mask         = (display_df["Date"] >= prev_start) & (display_df["Date"] <= prev_end) & (display_df["Next"] == True)
        display_df           = display_df[normal_mask | shifted_mask]
        display_df["Date"]   = display_df["Date"].dt.strftime("%Y-%m-%d")
        if "Diesel KM" not in display_df.columns:
            display_df["Diesel KM"] = 0
        display_df["Avg"] = (
            pd.to_numeric(display_df["Diesel KM"], errors="coerce") /
            pd.to_numeric(display_df["Diesel"], errors="coerce").replace(0, float("nan"))
        ).round(2)
        for col, default in [("Income", 0), ("Gross Income", 0), ("Remark", "")]:
            if col not in display_df.columns:
                display_df[col] = default
        display_df = display_df[["Date", "Status", "Driver Name", "Conductor Name",
                                  "Scheduled KM", "Actual KM", "Diesel", "Diesel KM",
                                  "Avg", "Income", "Gross Income", "Remark", "Next"]]
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
# 2. DRIVER SALARY
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
        "Transaction": st.column_config.SelectboxColumn("Transaction", options=["cash", "online"], default="cash"),
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
        save_driver_salary(cleaned_df, bus_number=bus_number)
        st.success("✅ Saved!")
        st.session_state.pop(key, None)
        st.session_state.pop(ed_key, None)  
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
        st.session_state[fetch_key] = get_driver_salary(bus_number=bus_number)
    fetched_df = st.session_state[fetch_key]

    if not fetched_df.empty:
        disp = fetched_df.copy()
        disp["Date"] = pd.to_datetime(disp["Date"])
        start, end   = _get_date_range(date.today().year, sal_month, sal_half)
        disp         = disp[(disp["Date"] >= start) & (disp["Date"] <= end)].copy()
        disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")

        st.data_editor(
            disp, use_container_width=True, hide_index=True, num_rows="dynamic",
            key=f"edit_sal_{bus_number}",
            column_config={
                "id":          None,
                "Date":        st.column_config.TextColumn("Date"),
                "Driver Name": st.column_config.TextColumn("Driver Name"),
                "Salary":      st.column_config.NumberColumn("Salary", min_value=0),
                "Transaction": st.column_config.TextColumn("Transaction"),
                "Updated By":  None,
            }
        )

        if st.button("💾 Update Salary", key=f"update_sal_{bus_number}"):
            sal_state = st.session_state.get(f"edit_sal_{bus_number}", {})
            for row_idx, changes in sal_state.get("edited_rows", {}).items():
                update_driver_salary(disp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(sal_state.get("deleted_rows", []), reverse=True):
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
        st.session_state.pop(ed_key, None)  
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
        start, end  = _get_date_range(date.today().year, exp_month, exp_period)
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
            exp_state = st.session_state.get(f"edit_exp_{bus_number}", {})
            for row_idx, changes in exp_state.get("edited_rows", {}).items():
                update_vehicle_expense(display_exp.iloc[row_idx]["id"], changes)
            for row_idx in sorted(exp_state.get("deleted_rows", []), reverse=True):
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
# 4. DIESEL VIEW — har row ka alag rate
# ──────────────────────────────────────────────
def diesel_view(bus_number: str = ""):
    st.markdown("### Diesel View ⛽")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        d_month = st.selectbox("Month", options=list(range(1, 13)),
                               index=date.today().month - 1,
                               format_func=lambda x: date(2000, x, 1).strftime("%B"),
                               key=f"diesel_month_{bus_number}")
    with col2:
        d_period = st.radio("Period", ["1-15", "16-31", "01-31"],
                            index=2, horizontal=True,
                            key=f"diesel_period_{bus_number}")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        load = st.button("🔄 Load", key=f"diesel_load_{bus_number}", use_container_width=True)

    # ✅ DB se rate + payment load karo (bus + month + period wise)
    state_key = f"diesel_state_{bus_number}_{d_month}_{d_period}"
    if state_key not in st.session_state or load:
        st.session_state[state_key] = get_diesel_rate_payment(bus_number, d_month, d_period)

    saved = st.session_state[state_key]

    universal_rate = st.number_input(
        "⛽ Set rate for whole table ",
        min_value=0.0, step=0.01, format="%.2f",
        value=saved["rate"],
        key=f"diesel_rate_input_{bus_number}_{d_month}_{d_period}"
    )

    fetch_key = f"diesel_df_{bus_number}"
    if load or fetch_key not in st.session_state:
        start, end = _get_date_range(date.today().year, d_month, d_period)
        raw_df = get_diesel_summary(
            bus_number,
            from_date=start.strftime("%Y-%m-%d"),
            to_date=end.strftime("%Y-%m-%d"),
        )
        if not raw_df.empty:
            raw_df["Rate (₹/L)"] = universal_rate
            # ✅ Per-date saved custom rates apply karo (override universal rate)
            row_rates = get_diesel_row_rates(bus_number, raw_df["Date"].astype(str).tolist())
            if row_rates:
                raw_df["Rate (₹/L)"] = raw_df["Date"].astype(str).map(row_rates).fillna(universal_rate)
        st.session_state[fetch_key] = raw_df

    df = st.session_state.get(fetch_key, pd.DataFrame())

    if df.empty:
        st.info("No diesel records found for this period.")
        return

    df = df.copy()
    if "Rate (₹/L)" not in df.columns:
        df["Rate (₹/L)"] = universal_rate

    ed_key = f"diesel_editor_{bus_number}"
    st.data_editor(
        df[["Date", "Diesel", "Rate (₹/L)"]],
        use_container_width=True,
        hide_index=True,
        key=ed_key,
        column_config={
            "Date":       st.column_config.TextColumn("Date", disabled=True),
            "Diesel":     st.column_config.NumberColumn("Diesel (L)", disabled=True, format="%.2f"),
            "Rate (₹/L)": st.column_config.NumberColumn("Rate (₹/L)", min_value=0.0,
                                                           step=0.01, format="%.2f"),
        }
    )

    # Per-row override apply + DB me persist karo
    editor_state = st.session_state.get(ed_key, {})
    display_df   = df.copy()
    row_rate_changed = False
    for row_idx, changes in editor_state.get("edited_rows", {}).items():
        for col, val in changes.items():
            if row_idx < len(display_df):
                display_df.at[row_idx, col] = val
                if col == "Rate (₹/L)":
                    row_date = str(display_df.at[row_idx, "Date"])
                    save_diesel_row_rate(bus_number, row_date, float(val))
                    row_rate_changed = True

    if row_rate_changed:
        # session state ko bhi update kar do taki dobara save na ho aur consistent rahe
        st.session_state[fetch_key] = display_df.copy()

    display_df["Rate (₹/L)"] = pd.to_numeric(display_df["Rate (₹/L)"], errors="coerce").fillna(universal_rate)
    display_df["Amount (₹)"] = (display_df["Diesel"] * display_df["Rate (₹/L)"]).round(2)

    # ✅ Full table with Amount column
    st.dataframe(
        display_df[["Date", "Diesel", "Rate (₹/L)", "Amount (₹)"]],
        use_container_width=True,
        hide_index=True,
    )

    total_diesel = display_df["Diesel"].sum()
    total_amount = display_df["Amount (₹)"].sum()

    # ── Summary ──
    st.markdown(f"""
    <div style='background:#1e1e3a;border-radius:10px;padding:16px 24px;margin:12px 0;
                display:flex;gap:40px;flex-wrap:wrap;'>
        <div>
            <div style='color:#aaa;font-size:0.85rem;'>Total Diesel</div>
            <div style='color:#7B8CFF;font-size:1.3rem;font-weight:bold;'>{total_diesel:.2f} L</div>
        </div>
        <div>
            <div style='color:#aaa;font-size:0.85rem;'>Total Amount</div>
            <div style='color:#FFB347;font-size:1.3rem;font-weight:bold;'>₹{total_amount:,.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Payment Status (editable + saved per bus+month+period) ──
    st.markdown("#### Payment Status")

    edit_mode_key = f"diesel_pay_edit_{bus_number}_{d_month}_{d_period}"
    if edit_mode_key not in st.session_state:
        st.session_state[edit_mode_key] = False

    is_locked = saved["payment_done"] and not st.session_state[edit_mode_key]

    pay_col1, pay_col2 = st.columns(2)
    with pay_col1:
        paid_amount = st.number_input(
            "Amount Paid (₹)", min_value=0.0, step=0.01, format="%.2f",
            value=saved["paid_amount"],
            disabled=is_locked,
            key=f"diesel_paid_input_{bus_number}_{d_month}_{d_period}"
        )
    with pay_col2:
        payment_done = st.checkbox(
            "✅ Payment Done",
            value=saved["payment_done"],
            disabled=is_locked,
            key=f"diesel_pay_chk_{bus_number}_{d_month}_{d_period}"
        )

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("💾 Save Rate & Payment", key=f"diesel_save_{bus_number}_{d_month}_{d_period}",
                     use_container_width=True):
            save_diesel_rate_payment(bus_number, d_month, d_period,
                                      universal_rate, paid_amount, payment_done)
            st.session_state[state_key] = {
                "rate": universal_rate, "paid_amount": paid_amount, "payment_done": payment_done
            }
            st.session_state[edit_mode_key] = False
            st.success("✅ Saved!")
            st.rerun()
    with btn_col2:
        if saved["payment_done"] and not st.session_state[edit_mode_key]:
            if st.button("✏️ Edit Payment", key=f"diesel_edit_{bus_number}_{d_month}_{d_period}",
                         use_container_width=True):
                st.session_state[edit_mode_key] = True
                st.rerun()

    remaining = total_amount - paid_amount
    if payment_done or remaining <= 0:
        st.markdown("""
        <div style='background:#1B5E20;border-radius:10px;padding:14px 24px;margin-top:10px;'>
            <span style='color:#69F0AE;font-size:1.1rem;font-weight:bold;'>✅ Fully Paid</span>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style='background:#4a1010;border-radius:10px;padding:14px 24px;margin-top:10px;
                    display:flex;justify-content:space-between;align-items:center;'>
            <span style='color:#FF5252;font-size:1.1rem;font-weight:bold;'>⚠️ Payment Pending</span>
            <span style='color:#FFB347;font-size:1.2rem;font-weight:bold;'>Remaining: ₹{remaining:,.2f}</span>
        </div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 5. SALARY CHECK
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
