import streamlit as st
import pandas as pd
from datetime import date
from src.ui.home_base_layout import home_layout


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
    st.markdown("### 🔧 Maintenance Manager ")
    st.caption("Choose Vehicle")

    if is_admin_or_manager():
        vehicles = BUS_NUMBERS
    else:
        accessible = get_accessible_vehicles()
        vehicles   = [b for b in BUS_NUMBERS if b in accessible]

    if not vehicles:
        st.warning("⚠️ No Vehicle access. Contact Admin....")
        return

    # ── Vehicle buttons — 2 per row ──
        col1, col2 = st.columns(2)
        with col1:
        if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()
    
    for row_start in range(0, len(vehicles), 2):
        row_vehicles = vehicles[row_start:row_start + 2]
        cols = st.columns(2)
        for i, bus in enumerate(row_vehicles):
            with cols[i]:
                if st.button(f"🚐 {bus}", key=f"maint_veh_{bus}", use_container_width=True):
                    st.session_state["maintenance_selected_vehicle"] = bus
                    st.rerun()

    st.divider()

    # ── Quick Overview — overdue/due-soon summary across vehicles ──
    st.markdown("#### 📊 Quick Overview")

    overview_rows = []
    for bus in vehicles:
        records_df = get_maintenance_records(bus)
        overdue_count = 0
        due_soon_count = 0

        if not records_df.empty:
            latest_per_type = records_df.groupby("Service Type")["Date"].max().to_dict()
            for _, r in records_df.iterrows():
                is_latest = (r["Date"] == latest_per_type[r["Service Type"]])
                if not is_latest:
                    continue  # sirf latest occurrence check karo har type ki
                prev_date, km_since = _compute_row_km(bus, r["Service Type"], r["Date"], True)

                overdue, due_soon = False, False
                if r["Next Due KM"]:
                    if km_since >= r["Next Due KM"]:
                        overdue = True
                    elif km_since >= 0.9 * r["Next Due KM"]:
                        due_soon = True
                if r["Next Due Date"]:
                    try:
                        nd = pd.to_datetime(r["Next Due Date"]).date()
                        if nd < date.today():
                            overdue = True
                        elif (nd - date.today()).days <= 7:
                            due_soon = True
                    except Exception:
                        pass

                if overdue:
                    overdue_count += 1
                elif due_soon:
                    due_soon_count += 1

        overview_rows.append({
            "bus": bus,
            "total_services": len(records_df),
            "overdue": overdue_count,
            "due_soon": due_soon_count,
        })

    ov_cols = st.columns(len(overview_rows))
    for i, row in enumerate(overview_rows):
        with ov_cols[i]:
            if row["overdue"] > 0:
                status_color, status_text = "#4d1a1a", f"🔴 {row['overdue']} overdue"
            elif row["due_soon"] > 0:
                status_color, status_text = "#4d3d1a", f"🟡 {row['due_soon']} due soon"
            else:
                status_color, status_text = "#1a3d1a", "🟢 All clear"

            st.markdown(f"""
            <div style='background:{status_color};border-radius:10px;padding:14px;text-align:center;'>
                <div style='color:#ccc;font-size:0.85rem;'>🚐 {row['bus']}</div>
                <div style='color:white;font-size:0.9rem;font-weight:bold;margin-top:4px;'>{status_text}</div>
                <div style='color:#aaa;font-size:0.75rem;margin-top:4px;'>{row['total_services']} service records</div>
            </div>
            """, unsafe_allow_html=True)

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
            m_garage = st.text_input("Garage Name", default='None', key=f"m_garage_{bus_number}")
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
