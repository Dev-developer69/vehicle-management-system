import streamlit as st
import pandas as pd
from datetime import date

from src.database.db import (
    save_vehicle_records,
    save_driver_salary,
    save_vehicle_expenses,
    get_vehicle_records,
    get_driver_salary,
    get_vehicle_expenses,
    get_salary_check,
    update_vehicle_expense,  
    delete_vehicle_expense,
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
            valid = df["Avg"].dropna()
            total[col] = round(float(valid.mean()), 2) if not valid.empty else 0.0
        elif col in numeric_cols:
            total[col] = round(float(df[col].sum()), 3)
        else:
            total[col] = ""
    return pd.DataFrame({k: [v] for k, v in total.items()})


# ──────────────────────────────────────────────
# 1. VEHICLE RECORDS
# ──────────────────────────────────────────────
def editable_grid(bus_number: str):
    numeric_cols = ["Scheduled KM", "Actual KM", "Diesel", "Avg"]
    key         = f"grid_{bus_number}"
    ed_key      = f"editor_{bus_number}"
    fetch_key   = f"fetched_{bus_number}"
    confirm_key = f"show_confirm_{bus_number}"
    pending_key = f"pending_df_{bus_number}"

    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame({
            "Date":           [date.today()],
            "Driver Name":    [None],
            "Conductor Name": [None],
            "Scheduled KM":   [466],
            "Actual KM":      [0],
            "Diesel":         [0],
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
            "Driver Name":    st.column_config.TextColumn("Driver Name"),
            "Conductor Name": st.column_config.TextColumn("Conductor Name"),
            "Scheduled KM":   st.column_config.NumberColumn("Scheduled KM", min_value=0, default=466),
            "Actual KM":      st.column_config.NumberColumn("Actual KM", min_value=0, default=0),
            "Diesel":         st.column_config.NumberColumn("Diesel", min_value=0, default=0),
        },
    )

    editor_state = st.session_state.get(ed_key, {})
    edited_df    = _apply_editor_state(st.session_state[key], editor_state)

    # ── Save / Confirm buttons ──
    if st.session_state.get(confirm_key):
        st.warning("⚠️ Duplicate dates exist. Update karna hai?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Update", key=f"yes_{bus_number}"):
                pending = st.session_state.get(pending_key)
                save_vehicle_records(bus_number, pending)
                st.success("✅ Updated!")
                st.session_state.pop(key, None)
                st.session_state.pop(fetch_key, None)
                st.session_state.pop(confirm_key, None)
                st.session_state.pop(pending_key, None)
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key=f"no_{bus_number}"):
                st.session_state.pop(confirm_key, None)
                st.session_state.pop(pending_key, None)
                st.rerun()
    else:
        if st.button("💾 Save Changes", key=f"save_{bus_number}", width='stretch', type='tertiary'):
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

            new_dates       = set(cleaned_df["Date"].astype(str).tolist())
            existing_dates  = set(fetched_df["Date"].astype(str).tolist()) if not fetched_df.empty else set()
            duplicate_dates = new_dates & existing_dates

            if duplicate_dates:
                st.session_state[pending_key] = cleaned_df
                st.session_state[confirm_key] = True
                st.rerun()
            else:
                save_vehicle_records(bus_number, cleaned_df)
                st.success("✅ Saved!")
                st.session_state.pop(key, None)
                st.session_state.pop(fetch_key, None)
                st.rerun()

    # ── Saved Records display ──
    st.markdown("### Saved Records 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_records(bus_number)

    fetched_df = st.session_state[fetch_key]

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        from_date = st.date_input("From", value=None, key=f"from_{bus_number}", format="YYYY-MM-DD")
    with col2:
        to_date = st.date_input("To", value=None, key=f"to_{bus_number}", format="YYYY-MM-DD")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key=f"refresh_{bus_number}",width='stretch', type='tertiary'):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        display_df = fetched_df.copy()
        display_df["Date"] = pd.to_datetime(display_df["Date"])

        if from_date is not None:
            display_df = display_df[display_df["Date"] >= pd.Timestamp(from_date)]
        if to_date is not None:
            display_df = display_df[display_df["Date"] <= pd.Timestamp(to_date)]

        if from_date is None and to_date is None:
            display_df = display_df.head(15)

        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        display_df["Avg"] = (
            display_df["Actual KM"] / display_df["Diesel"].replace(0, float("nan"))
        ).round(2)

        # Data alag, total alag
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Total row hamesha neeche fixed
        total_row = build_total_row(display_df, numeric_cols, label_col="Driver Name")
        st.dataframe(total_row, use_container_width=True, hide_index=True)
    else:
        st.info("No records found.")


# ──────────────────────────────────────────────
# 2. DRIVER SALARY
# ──────────────────────────────────────────────
def driver_salary(bus_number: str = ""):
    key         = f"driver_salary_{bus_number}"
    ed_key      = f"editor_salary_{bus_number}"
    fetch_key   = f"fetched_salary_{bus_number}"
    confirm_key = f"show_confirm_salary_{bus_number}"
    pending_key = f"pending_df_salary_{bus_number}"

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

    # ── Save / Confirm buttons ──
    if st.session_state.get(confirm_key):
        st.warning("⚠️ Duplicate dates exist. Update karna hai?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Update", key=f"yes_salary_{bus_number}"):
                pending = st.session_state.get(pending_key)
                save_driver_salary(pending)
                st.success("✅ Updated!")
                st.session_state.pop(key, None)
                st.session_state.pop(fetch_key, None)
                st.session_state.pop(confirm_key, None)
                st.session_state.pop(pending_key, None)
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key=f"no_salary_{bus_number}"):
                st.session_state.pop(confirm_key, None)
                st.session_state.pop(pending_key, None)
                st.rerun()
    else:
        if st.button("💾 Save Changes", key=f"save_salary_{bus_number}"):
            cleaned_df = edited_df[
                edited_df["Driver Name"].notna() &
                (edited_df["Driver Name"].astype(str).str.strip() != "")
            ].copy()

            if cleaned_df.empty:
                st.warning("⚠️ No valid rows to save.")
                return

            if fetch_key not in st.session_state:
                st.session_state[fetch_key] = get_driver_salary()
            fetched_df = st.session_state[fetch_key]

            new_dates       = set(cleaned_df["Date"].astype(str).tolist())
            existing_dates  = set(fetched_df["Date"].astype(str).tolist()) if not fetched_df.empty else set()
            duplicate_dates = new_dates & existing_dates

            if duplicate_dates:
                st.session_state[pending_key] = cleaned_df
                st.session_state[confirm_key] = True
                st.rerun()
            else:
                save_driver_salary(cleaned_df)
                st.success("✅ Saved!")
                st.session_state.pop(key, None)
                st.session_state.pop(fetch_key, None)
                st.rerun()

    # ── Saved Records display ──
    st.markdown("### Saved Salary Records 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_driver_salary()

    fetched_df = st.session_state[fetch_key]
    if not fetched_df.empty:
        total_row = build_total_row(fetched_df, ["Salary"], label_col="Driver Name")
        st.dataframe(
            pd.concat([fetched_df, total_row], ignore_index=True),
            use_container_width=True,
            hide_index=True,
        )
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

    # ── Saved Expenses display ──
    st.markdown("### Saved Expenses 📋")
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_vehicle_expenses(bus_number)

    fetched_df = st.session_state[fetch_key]

    col_r, col_ref = st.columns([5, 1])
    with col_ref:
        if st.button("🔄", key=f"ref_exp_{bus_number}"):
            st.session_state.pop(fetch_key, None)
            st.rerun()

    if not fetched_df.empty:
        # Editable table — id hidden
        edited = st.data_editor(
            fetched_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"edit_exp_{bus_number}",
            column_config={
                "id":           None,
                "Date":        st.column_config.TextColumn("Date"),  # DateColumn → TextColumn
                "Category":    st.column_config.TextColumn("Category"),
                "Amount":      st.column_config.NumberColumn("Amount", min_value=0),
                "Description": st.column_config.TextColumn("Description"),
            }
        )

        if st.button("💾 Update Expenses", key=f"update_exp_{bus_number}"):
            from src.database.db import update_vehicle_expense, delete_vehicle_expense
            editor_state = st.session_state.get(f"edit_exp_{bus_number}", {})

            for row_idx, changes in editor_state.get("edited_rows", {}).items():
                expense_id = fetched_df.iloc[row_idx]["id"]
                update_vehicle_expense(expense_id, changes)

            for row_idx in sorted(editor_state.get("deleted_rows", []), reverse=True):
                expense_id = fetched_df.iloc[row_idx]["id"]
                delete_vehicle_expense(expense_id)

            st.success("✅ Updated!")
            st.session_state.pop(fetch_key, None)
            st.rerun()
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
