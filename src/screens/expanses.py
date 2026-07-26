import streamlit as st
import pandas as pd
import calendar
from datetime import date
from src.ui.home_base_layout import home_layout
from src.database.db import (
    get_vehicle_expenses, get_driver_salary,
    get_diesel_rate_payment, get_diesel_summary,
    get_maintenance_records,
)
from src.database.auth import get_accessible_vehicles
from src.ui.excel_format import _get_date_range

ALL_BUSES = [("3131", "3131_E"), ("0303", "0303_E"), ("7389", "7389_E"), ("2350", "2350_E")]


def _get_diesel_cost(bus: str, start, end, month: int, period: str) -> float:
    diesel_df = get_diesel_summary(bus, str(start.date()), str(end.date()))
    if diesel_df.empty:
        return 0.0
    total_diesel = diesel_df["Diesel"].sum()
    rate_data    = get_diesel_rate_payment(bus, month, period)
    return round(total_diesel * rate_data["rate"], 2)


def _get_salary_cost(bus: str, start, end) -> float:
    sal_df = get_driver_salary(bus_number=bus)
    if sal_df.empty:
        return 0.0
    sal_df["Date"] = pd.to_datetime(sal_df["Date"])
    sal_df = sal_df[(sal_df["Date"] >= start) & (sal_df["Date"] <= end)]
    return float(sal_df["Salary"].sum()) if not sal_df.empty else 0.0


def _get_maintenance_cost(bus: str, start, end) -> float:
    maint_df = get_maintenance_records(bus)
    if maint_df.empty:
        return 0.0
    maint_df["Date"] = pd.to_datetime(maint_df["Date"])
    maint_df = maint_df[(maint_df["Date"] >= start) & (maint_df["Date"] <= end)]
    return float(maint_df["Cost"].sum()) if not maint_df.empty else 0.0


def _show_bus_detail(bus: str, start, end, month: int, period: str):
    exp_df = get_vehicle_expenses(bus)
    if not exp_df.empty:
        exp_df["Date"] = pd.to_datetime(exp_df["Date"])
        exp_df = exp_df[(exp_df["Date"] >= start) & (exp_df["Date"] <= end)]

    vehicle_exp_total = float(exp_df["Amount"].sum()) if not exp_df.empty else 0.0
    diesel_cost  = _get_diesel_cost(bus, start, end, month, period)
    salary_cost  = _get_salary_cost(bus, start, end)
    maint_cost   = _get_maintenance_cost(bus, start, end)
    grand_total  = vehicle_exp_total + diesel_cost + salary_cost + maint_cost

    st.markdown(f"""
    <div style='background:#1E1E3A;border-radius:16px;padding:24px;
                border:1px solid #7B8CFF;margin:12px 0;'>
        <div style='font-size:1.3rem;font-weight:700;color:#7B8CFF;margin-bottom:16px;'>
            🚌 Bus {bus} — Detailed Expenses
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🧾 Vehicle Exp",  f"₹{vehicle_exp_total:,.0f}")
    c2.metric("⛽ Diesel",       f"₹{diesel_cost:,.0f}")
    c3.metric("👤 Salary",       f"₹{salary_cost:,.0f}")
    c4.metric("🔧 Maintenance",  f"₹{maint_cost:,.0f}")
    c5.metric("📊 Grand Total",  f"₹{grand_total:,.0f}")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if not exp_df.empty:
        st.markdown("**🧾 Vehicle Expenses — Category wise:**")
        cat_df = exp_df.groupby("Category")["Amount"].sum().reset_index()
        cat_df = cat_df.sort_values("Amount", ascending=False)
        cat_df["Amount"] = cat_df["Amount"].apply(lambda x: f"₹{x:,.0f}")
        st.dataframe(cat_df, use_container_width=True, hide_index=True)

    sal_df = get_driver_salary(bus_number=bus)
    if not sal_df.empty:
        sal_df["Date"] = pd.to_datetime(sal_df["Date"])
        sal_df = sal_df[(sal_df["Date"] >= start) & (sal_df["Date"] <= end)]
        if not sal_df.empty:
            st.markdown("**👤 Driver Salary Records:**")
            show_sal = sal_df[["Date", "Driver Name", "Salary", "Transaction"]].copy()
            show_sal["Date"]   = show_sal["Date"].dt.strftime("%Y-%m-%d")
            show_sal["Salary"] = show_sal["Salary"].apply(lambda x: f"₹{x:,.0f}")
            st.dataframe(show_sal, use_container_width=True, hide_index=True)

    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#2D2D5E,#1E1E3A);border-radius:12px;
                padding:16px;text-align:center;margin-top:12px;border:1px solid #7B8CFF;'>
        <span style='color:#aaa;font-size:0.9rem;'>Grand Total — Bus {bus}: </span>
        <span style='color:#7B8CFF;font-size:1.6rem;font-weight:bold;'>₹{grand_total:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)


def expenses():
    if st.button('Home page', type='secondary', width='stretch',
                 icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()

    home_layout()
    st.markdown("<h2 style='text-align:center;'>Expenses 🧾</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    accessible    = get_accessible_vehicles()
    visible_buses = [(bus, state) for bus, state in ALL_BUSES if bus in accessible]

    if not visible_buses:
        st.warning("⚠️ Aapko kisi bhi vehicle ka access nahi hai.")
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
    fc1, fc2, fc3 = st.columns([2, 3, 1])
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
            "Period", ["1-15", "16-31", "01-31"],
            index=2, horizontal=True, key="summary_period",
        )
    with fc3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", key="exp_refresh", use_container_width=True):
            for bus, _ in visible_buses:
                st.session_state.pop(f"exp_cache_{bus}", None)
            st.session_state["open_bus_detail"] = None
            st.rerun()

    year       = date.today().year
    start, end = _get_date_range(year, summary_month, summary_period)

    # ── Per bus totals (cached) ──
    bus_data = {}
    for bus, _ in visible_buses:
        cache_key = f"exp_cache_{bus}_{summary_month}_{summary_period}"
        if cache_key not in st.session_state:
            exp_df = get_vehicle_expenses(bus)
            if not exp_df.empty:
                exp_df["Date"] = pd.to_datetime(exp_df["Date"])
                exp_df = exp_df[(exp_df["Date"] >= start) & (exp_df["Date"] <= end)]
                vehicle_exp = float(exp_df["Amount"].sum()) if not exp_df.empty else 0.0
            else:
                vehicle_exp = 0.0
            diesel_cost = _get_diesel_cost(bus, start, end, summary_month, summary_period)
            salary_cost = _get_salary_cost(bus, start, end)
            maint_cost  = _get_maintenance_cost(bus, start, end)
            st.session_state[cache_key] = {
                "vehicle_exp": vehicle_exp,
                "diesel":      diesel_cost,
                "salary":      salary_cost,
                "maint":       maint_cost,
                "total":       vehicle_exp + diesel_cost + salary_cost + maint_cost,
            }
        bus_data[bus] = st.session_state[cache_key]

    # ── Summary Cards ──
    card_cols = st.columns(len(visible_buses))
    for i, (bus, _) in enumerate(visible_buses):
        d = bus_data[bus]
        with card_cols[i]:
            is_open = st.session_state.get("open_bus_detail") == bus

            # Card HTML
            border = "2px solid #7B8CFF" if is_open else "1px solid #2D2D5E"
            st.markdown(f"""
            <div style='background:#1E1E3A;border-radius:14px;padding:20px;
                        text-align:center;border:{border};margin-bottom:4px;'>
                <div style='font-size:1.7rem;color:#7B8CFF;font-weight:bold;'>
                    ₹{d["total"]:,.0f}
                </div>
                <div style='color:#ccc;margin-top:6px;font-size:0.95rem;font-weight:600;'>
                    Bus {bus}
                </div>
                <div style='color:#888;margin-top:6px;font-size:0.75rem;'>
                    Exp ₹{d["vehicle_exp"]:,.0f} · Diesel ₹{d["diesel"]:,.0f}
                    · Salary ₹{d["salary"]:,.0f}
                </div>
                <div style='color:#7B8CFF;margin-top:8px;font-size:0.8rem;'>
                    {"▲ Tap to close" if is_open else "▼ Tap for breakdown →"}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Toggle button (invisible — sits over the card visually)
            if st.button(
                "▼ Details" if not is_open else "▲ Close",
                key=f"card_toggle_{bus}",
                use_container_width=True,
                type="secondary",
            ):
                if is_open:
                    st.session_state["open_bus_detail"] = None
                else:
                    # ✅ sirf ek hi open — baaki sab band
                    st.session_state["open_bus_detail"] = bus
                st.rerun()

    # ── Detail view — sirf ek bus ka ──
    open_bus = st.session_state.get("open_bus_detail")
    if open_bus and open_bus in [b for b, _ in visible_buses]:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        _show_bus_detail(open_bus, start, end, summary_month, summary_period)
        st.markdown("---")

    # ── Grand total ──
    st.markdown("<br>", unsafe_allow_html=True)
    grand_total = sum(d["total"] for d in bus_data.values())
    st.markdown(f"""
    <div style='background:#2D2D5E;border-radius:12px;padding:16px;text-align:center;'>
        <span style='color:#aaa;font-size:1rem;'>Total Expenses (All Buses): </span>
        <span style='color:#9B59B6;font-size:1.5rem;font-weight:bold;'>₹{grand_total:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style='position:fixed;bottom:20px;width:100%;text-align:center;color:white;font-size:0.9rem;'>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>""", unsafe_allow_html=True)
