import streamlit as st
import pandas as pd
from datetime import date

from src.database.db import (
    get_maintenance_records, save_maintenance_record, delete_maintenance_record,
    get_previous_service_date, get_km_between,
)
from src.database.auth import get_accessible_vehicles, is_admin_or_manager

BUS_NUMBERS = ["0303", "2350", "7389", "3131"]


def _compute_row_km(bus_number: str, service_type: str, record_date, is_latest: bool):
    prev_date = get_previous_service_date(bus_number, service_type, record_date)
    end_date  = date.today() if is_latest else record_date
    km_since  = get_km_between(bus_number, prev_date, end_date)
    return prev_date, km_since


def _highlight_due(row):
    overdue, due_soon = False, False

    km_left  = row["Next Due KM"]
    km_since = row["KM Since Last Service"]
    if km_left not in ("—", None):
        if km_since >= km_left:
            overdue = True
        elif km_since >= 0.9 * km_left:
            due_soon = True

    due_date = row["Next Due Date"]
    if due_date not in ("—", None):
        try:
            nd = pd.to_datetime(due_date).date()
            if nd < date.today():
                overdue = True
            elif (nd - date.today()).days <= 7:
                due_soon = True
        except Exception:
            pass

    if overdue:
        return ["background-color: #4d1a1a"] * len(row)
    elif due_soon:
        return ["background-color: #4d3d1a"] * len(row)
    return [""] * len(row)


# ──────────────────────────────────────────────
# 1. VEHICLE SELECTOR
# ──────────────────────────────────────────────
def _maintenance_home():
    st.markdown("### 🔧 Maintenance Manager")
    st.caption("Vehicle chuno maintenance records dekhne/add karne ke liye")

    if is_admin_or_manager():
        vehicles = BUS_NUMBERS
    else:
        accessible = get_accessible_vehicles()
        vehicles   = [b for b in BUS_NUMBERS if b in accessible]

    if not vehicles:
        st.warning("⚠️ Koi vehicle access nahi hai. Admin se contact karo.")
        return

    cols = st.columns(len(vehicles))
    for i, bus in enumerate(vehicles):
        with cols[i]:
            if st.button(f"🚐 {bus}", key=f"maint_veh_{bus}", use_container_width=True):
                st.session_state["maintenance_selected_vehicle"] = bus
                st.rerun()


# ──────────────────────────────────────────────
# 2. PER-VEHICLE MAINTENANCE GRID
# ──────────────────────────────────────────────
def _maintenance_vehicle_page():
    bus_number = st.session_state.get("maintenance_selected_vehicle")

    if st.button("⬅️ Back to Vehicles", key="maint_back_veh"):
        st.session_state.pop("maintenance_selected_vehicle", None)
        st.rerun()

    st.markdown(f"### 🔧 Maintenance Records — {bus_number} 🚐")

    user          = st.session_state.get("user")
    current_email = user.email if user else "unknown"

    # ── Add / Update form ──
    with st.container(border=True):
        st.markdown("#### ➕ Add / Update Service Record")

        c1, c2 = st.columns(2)
        with c1:
            m_date = st.date_input("Service Date", value=date.today(), key=f"m_date_{bus_number}")
        with c2:
            m_type = st.text_input("Service Type", key=f"m_type_{bus_number}",
                                    placeholder="e.g. Oil Change")

        c3, c4 = st.columns(2)
        with c3:
            m_garage = st.text_input("Garage Name", key=f"m_garage_{bus_number}")
        with c4:
            m_cost = st.number_input("Cost (₹)", min_value=0.0, step=0.01, key=f"m_cost_{bus_number}")

        c5, c6 = st.columns(2)
        with c5:
            m_next_date = st.date_input("Next Due Date (optional)", value=None, key=f"m_next_date_{bus_number}")
        with c6:
            m_next_km = st.number_input("Next Due KM (optional)", min_value=0, step=1, key=f"m_next_km_{bus_number}")

        m_notes = st.text_input("Notes", key=f"m_notes_{bus_number}", placeholder="optional...")

        if st.button("💾 Save Record", key=f"m_save_{bus_number}", type="primary", use_container_width=True):
            if not m_type.strip():
                st.warning("⚠️ Service Type required.")
            else:
                save_maintenance_record(
                    bus_number, m_date, m_type, m_garage, m_cost, m_notes,
                    m_next_date, m_next_km if m_next_km else None, current_email,
                )
                st.success(f"✅ Saved: {m_type} on {m_date}")
                st.session_state.pop(f"maint_records_{bus_number}", None)
                st.rerun()

    st.markdown("### 📋 Saved Maintenance Records")

    fetch_key = f"maint_records_{bus_number}"
    if fetch_key not in st.session_state:
        st.session_state[fetch_key] = get_maintenance_records(bus_number)
    records_df = st.session_state[fetch_key]

    if records_df.empty:
        st.info("No maintenance records found.")
        return

    # latest record per service_type -> "ongoing" row (KM keeps counting from it till today)
    latest_per_type = records_df.groupby("Service Type")["Date"].max().to_dict()

    display_rows = []
    for _, r in records_df.iterrows():
        is_latest = (r["Date"] == latest_per_type[r["Service Type"]])
        prev_date, km_since = _compute_row_km(bus_number, r["Service Type"], r["Date"], is_latest)
        display_rows.append({
            "Date":                   r["Date"],
            "Service Type":           r["Service Type"],
            "Garage":                 r["Garage"],
            "Cost":                   r["Cost"],
            "Last Service Date":      prev_date or "—",
            "KM Since Last Service":  km_since,
            "Next Due Date":          r["Next Due Date"] or "—",
            "Next Due KM":            r["Next Due KM"] or "—",
            "Notes":                  r["Notes"],
        })

    display_df = pd.DataFrame(display_rows)
    styled = display_df.style.apply(_highlight_due, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Delete record ──
    with st.expander("🗑️ Delete a record"):
        options = {
            f"{row['Date']} — {row['Service Type']}": row["id"]
            for _, row in records_df.iterrows()
        }
        sel = st.selectbox("Select record to delete", list(options.keys()), key=f"m_del_sel_{bus_number}")
        if st.button("Delete this record", key=f"m_del_btn_{bus_number}", type="primary"):
            delete_maintenance_record(bus_number, options[sel])
            st.success(f"✅ Deleted: {sel}")
            st.session_state.pop(fetch_key, None)
            st.rerun()


# ──────────────────────────────────────────────
# ENTRY POINT — app.py isi ko call karega
# ──────────────────────────────────────────────
def maintenance_page():
    if st.session_state.get("maintenance_selected_vehicle"):
        _maintenance_vehicle_page()
    else:
        _maintenance_home()
