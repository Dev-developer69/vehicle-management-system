import streamlit as st
import pandas as pd
from src.ui.home_base_layout import home_layout
from src.database.db import get_vehicle_expenses
from src.database.auth import get_accessible_vehicles


allowed = get_accessible_vehicles()
role = get_current_role()
st.write(f"Role: {role}")
st.write(f"Allowed buses: {allowed}")


def expenses():
    if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()
    home_layout()
    st.markdown("<h2 style='text-align:center;'>Expenses 🧾</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Sirf allowed buses — admin/manager ko sab, subordinate ko assigned waali
    allowed_buses = get_accessible_vehicles()

    # Saari buses ki mapping (button state ke saath)
    ALL_BUSES = [("3131", "3131_E"), ("0303", "0303_E"), ("7389", "7389_E"), ("2350", "2350_E")]

    # Filter: sirf woh buses dikhao jo allowed hain
    visible_buses = [(bus, state) for bus, state in ALL_BUSES if bus in allowed_buses]

    # ── Vehicle buttons ──
    col1, col2 = st.columns(2, gap='small')
    for i, (bus, state) in enumerate(visible_buses):
        col = col1 if i % 2 == 0 else col2
        with col:
            if st.button(f"🚌 Bus {bus}", type='secondary', width='stretch', key=f"exp_btn_{bus}"):
                st.session_state['login_state'] = state
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Summary cards ──
    st.markdown("### Expenses Summary 📊")
    all_expenses = []
    for bus, _ in visible_buses:
        df = get_vehicle_expenses(bus)
        if not df.empty:
            df["bus_number"] = bus
            all_expenses.append(df)

    if all_expenses:
        combined = pd.concat(all_expenses, ignore_index=True)
        totals = combined.groupby("bus_number")["Amount"].sum()

        # Dynamically columns banao based on visible buses
        cols = st.columns(len(visible_buses))
        for i, (bus, _) in enumerate(visible_buses):
            with cols[i]:
                st.markdown(f"""
                <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                    <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get(bus, 0):,.0f}</div>
                    <div style='color:#aaa;margin-top:8px;'>Bus {bus}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Grand total
        grand_total = combined["Amount"].sum()
        st.markdown(f"""
        <div style='background:#2D2D5E;border-radius:12px;padding:16px;text-align:center;'>
            <span style='color:#aaa;font-size:1rem;'>Total Expenses (All Buses): </span>
            <span style='color:#9B59B6;font-size:1.5rem;font-weight:bold;'>₹{grand_total:,.0f}</span>
        </div>""", unsafe_allow_html=True)
    else:
        st.info("No expense data found.")

    st.markdown("""
    <div style='
        position: fixed;
        bottom: 20px;
        width: 100%;
        text-align: center;
        color: white;
        font-size: 0.9rem;
    '>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>
""", unsafe_allow_html=True)
