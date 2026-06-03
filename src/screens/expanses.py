import streamlit as st
from src.ui.home_base_layout import home_layout
from src.database.db import get_vehicle_expenses

def expenses():
    if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()
    home_layout()

    st.markdown("<h2 style='text-align:center;'>Expenses 🧾</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Vehicle buttons ──
    col1, col2 = st.columns(2, gap='small')
    buses = [("3131", "3131_E"), ("0303", "0303_E"), ("7389", "7389_E"), ("2350", "2350_E")]

    for i, (bus, state) in enumerate(buses):
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
    for bus, _ in buses:
        df = get_vehicle_expenses(bus)
        if not df.empty:
            df["bus_number"] = bus
            all_expenses.append(df)

    if all_expenses:
        import pandas as pd
        combined = pd.concat(all_expenses, ignore_index=True)

        c1, c2, c3, c4 = st.columns(4)
        totals = combined.groupby("bus_number")["Amount"].sum()

        with c1:
            st.markdown(f"""
            <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get("3131", 0):,.0f}</div>
                <div style='color:#aaa;margin-top:8px;'>Bus 3131</div>
            </div>""", unsafe_allow_html=True)

        with c2:
            st.markdown(f"""
            <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get("0303", 0):,.0f}</div>
                <div style='color:#aaa;margin-top:8px;'>Bus 0303</div>
            </div>""", unsafe_allow_html=True)

        with c3:
            st.markdown(f"""
            <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get("7389", 0):,.0f}</div>
                <div style='color:#aaa;margin-top:8px;'>Bus 7389</div>
            </div>""", unsafe_allow_html=True)

        with c4:
            st.markdown(f"""
            <div style='background:#1E1E3A;border-radius:12px;padding:20px;text-align:center;border:1px solid #2D2D5E;'>
                <div style='font-size:1.8rem;color:#7B8CFF;font-weight:bold;'>₹{totals.get("2350", 0):,.0f}</div>
                <div style='color:#aaa;margin-top:8px;'>Bus 2350</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Total across all buses
        grand_total = combined["Amount"].sum()
        st.markdown(f"""
        <div style='background:#2D2D5E;border-radius:12px;padding:16px;text-align:center;'>
            <span style='color:#aaa;font-size:1rem;'>Total Expenses (All Buses): </span>
            <span style='color:#9B59B6;font-size:1.5rem;font-weight:bold;'>₹{grand_total:,.0f}</span>
        </div>""", unsafe_allow_html=True)
    else:
        st.info("No expense data found.")