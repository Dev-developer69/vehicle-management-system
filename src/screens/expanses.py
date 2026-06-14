import streamlit as st
import pandas as pd
import calendar
from datetime import date
from src.ui.home_base_layout import home_layout
from src.database.db import get_vehicle_expenses
from src.database.auth import get_accessible_vehicles

ALL_BUSES = [("3131", "3131_E"), ("0303", "0303_E"), ("7389", "7389_E"), ("2350", "2350_E")]


def _get_date_range(year: int, month: int, period: str):
    if period == "1-15":
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 15)
    elif period == "16-31":
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 16), pd.Timestamp(year, month, last_day)
    else:  # 01-31
        last_day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, 1), pd.Timestamp(year, month, last_day)


def expenses():
    if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()
    home_layout()
    st.markdown("<h2 style='text-align:center;'>Expenses 🧾</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    accessible    = get_accessible_vehicles()
    visible_buses = [(bus, state) for bus, state in ALL_BUSES if bus in accessible]

    if not visible_buses:
        st.warning("⚠️ Aapko kisi bhi vehicle ka access nahi hai. Admin se contact karo.")
        return

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

    # ── Period filter ──
    st.markdown("### Expenses Summary 📊")
    fc1, fc2 = st.columns([2, 3])
    with fc1:
        summary_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda x: date(2000, x, 1).strftime("%B"),
            key="summary_month",
        )
    with fc2:
        summary_period = st.radio(
            "Period",
            ["1-15", "16-31", "01-31"],
            index=2,
            horizontal=True,
            key="summary_period",
        )

    year        = date.today().year
    start, end  = _get_date_range(year, summary_month, summary_period)

    # ── Summary cards ──
    all_expenses = []
    for bus, _ in visible_buses:
        df = get_vehicle_expenses(bus)
        if not df.empty:
            df["bus_number"] = bus
            df["Date"]       = pd.to_datetime(df["Date"])
            df = df[(df["Date"] >= start) & (df["Date"] <= end)]
            if not df.empty:
                all_expenses.append(df)

    if all_expenses:
        combined = pd.concat(all_expenses, ignore_index=True)
        totals   = combined.groupby("bus_number")["Amount"].sum()

        card_cols = st.columns(len(visible_buses))
        for i, (bus, _) in enumerate(visible_buses):
            with card_cols[i]:
                st.markdown(f"""
                <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                    <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get(bus, 0):,.0f}</div>
                    <div style='color:#aaa;margin-top:8px;'>Bus {bus}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        grand_total = combined["Amount"].sum()
        st.markdown(f"""
        <div style='background:#2D2D5E;border-radius:12px;padding:16px;text-align:center;'>
            <span style='color:#aaa;font-size:1rem;'>Total Expenses (All Buses): </span>
            <span style='color:#9B59B6;font-size:1.5rem;font-weight:bold;'>₹{grand_total:,.0f}</span>
        </div>""", unsafe_allow_html=True)
    else:
        st.info("No expense data found for selected period.")

    st.markdown("""
    <div style='position:fixed;bottom:20px;width:100%;text-align:center;color:white;font-size:0.9rem;'>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>""", unsafe_allow_html=True)
