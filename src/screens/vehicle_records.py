import calendar
import streamlit as st
import pandas as pd
from datetime import date
from src.ui.home_base_layout import home_layout
from src.database.auth import get_accessible_vehicles
from src.database.config import supabase

VEHICLE_MAP = {
    "7389": "page_7389",
    "2350": "page_2350",
    "0303": "page_0303",
    "3131": "page_3131",
}


def _get_current_period():
    today    = date.today()
    year     = today.year
    month    = today.month
    if today.day <= 15:
        period   = "1-15"
        start    = date(year, month, 1)
        end      = date(year, month, 15)
    else:
        last_day = calendar.monthrange(year, month)[1]
        period   = "16-31"
        start    = date(year, month, 16)
        end      = date(year, month, last_day)
    return period, start, end


def vehicle_records():
    col1, col2 = st.columns(2)
    with col1:
        st.header("Select Vehicle", text_alignment='center')
    with col2:
        if st.button('Home page', type='primary', width='stretch',
                     icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state'] = None
            st.rerun()

    home_layout()

    accessible       = get_accessible_vehicles()
    visible_vehicles = [bus for bus in VEHICLE_MAP.keys() if bus in accessible]

    if not visible_vehicles:
        st.warning("⚠️ Aapko kisi bhi vehicle ka access nahi diya gaya. Admin se contact karo.")
    else:
        cols = st.columns(2)
        for i, bus in enumerate(visible_vehicles):
            with cols[i % 2]:
                btn_type = 'secondary' if i < 2 else 'tertiary'
                if st.button(
                    bus,
                    type=btn_type,
                    key=f"btn_v_{bus}",
                    width='stretch',
                    icon=':material/bus_railway:',
                    icon_position='right'
                ):
                    st.session_state['login_state'] = VEHICLE_MAP[bus]
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    quick_overview(visible_vehicles)

    st.markdown("""
        <div style='position:fixed;bottom:20px;width:100%;text-align:center;
                    color:white;font-size:0.9rem;'>
            <p>Created with ❤️ by Dev-developer69</p>
        </div>
    """, unsafe_allow_html=True)


def quick_overview(bus_list: list):
    if not bus_list:
        return

    period, start, end = _get_current_period()
    period_label       = f"{date.today().strftime('%B')} ({period})"

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:10px;margin-bottom:0.5rem;'>
        <span style='font-size:1.5rem;'>📊</span>
        <span style='font-size:1.2rem;font-weight:600;'>Quick Overview</span>
        <span style='font-size:0.85rem;color:#aaa;margin-left:8px;'>{period_label}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Fetch data from DB ──
    overview_cache_key = f"overview_{start}_{end}"
    if overview_cache_key not in st.session_state:
        res = supabase.table("vehicle_records") \
            .select("bus_number, income, diesel, actual_km, status") \
            .in_("bus_number", bus_list) \
            .gte("date", str(start)) \
            .lte("date", str(end)) \
            .execute()
        st.session_state[overview_cache_key] = res.data or []

    rows = st.session_state[overview_cache_key]

    if not rows:
        st.info("Is period mein koi record nahi mila.")
        return

    df = pd.DataFrame(rows)
    df = df[df["status"] != "On Leave"]
    df["income"]     = pd.to_numeric(df["income"],     errors="coerce").fillna(0)
    df["diesel"]     = pd.to_numeric(df["diesel"],     errors="coerce").fillna(0)
    df["actual_km"]  = pd.to_numeric(df["actual_km"],  errors="coerce").fillna(0)

    summary = df.groupby("bus_number").agg(
        Income   =("income",    "sum"),
        Diesel   =("diesel",    "sum"),
        Actual_KM=("actual_km", "sum"),
        Days     =("income",    "count"),
    ).reset_index().rename(columns={"bus_number": "Bus"})

    # ── Summary cards ──
    card_cols = st.columns(len(summary))
    for i, (_, row) in enumerate(summary.iterrows()):
        with card_cols[i]:
            st.markdown(f"""
            <div style='background:#14A085;border-radius:12px;padding:16px;
                        text-align:center;border:1px solid rgba(255,255,255,0.2);'>
                <div style='font-size:1.1rem;font-weight:600;color:white;
                            margin-bottom:8px;'>🚌 {row["Bus"]}</div>
                <div style='color:#d0f5ee;font-size:0.8rem;'>Income</div>
                <div style='color:white;font-size:1.3rem;font-weight:700;'>
                    ₹{int(row["Income"]):,}</div>
                <div style='color:#d0f5ee;font-size:0.8rem;margin-top:6px;'>Diesel</div>
                <div style='color:#FFD700;font-size:1.1rem;font-weight:600;'>
                    {row["Diesel"]:.1f} L</div>
                <div style='color:#d0f5ee;font-size:0.75rem;margin-top:6px;'>
                    {int(row["Days"])} days · {int(row["Actual_KM"])} km</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Bar Chart — Income + Diesel per Bus ──
    chart_tab1, chart_tab2 = st.tabs(["💰 Income", "⛽ Diesel"])

    with chart_tab1:
        income_df = summary[["Bus", "Income"]].set_index("Bus")
        st.bar_chart(income_df, color="#14A085", use_container_width=True)

    with chart_tab2:
        diesel_df = summary[["Bus", "Diesel"]].set_index("Bus")
        st.bar_chart(diesel_df, color="#FFB347", use_container_width=True)

    # ── Refresh button ──
    if st.button("🔄 Refresh Overview", key="refresh_overview"):
        st.session_state.pop(overview_cache_key, None)
        st.rerun()
