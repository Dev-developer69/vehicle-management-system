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
    today = date.today()
    year  = today.year
    month = today.month
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

    # ── Fetch from DB ──
    cache_key = f"overview_{start}_{end}"
    if cache_key not in st.session_state:
        res = supabase.table("vehicle_records") \
            .select("bus_number, date, driver_name, actual_km, scheduled_km, income, diesel, status") \
            .in_("bus_number", bus_list) \
            .gte("date", str(start)) \
            .lte("date", str(end)) \
            .order("date", desc=False) \
            .execute()
        st.session_state[cache_key] = res.data or []

    rows = st.session_state[cache_key]

    if not rows:
        st.info("Is period mein koi record nahi mila.")
        if st.button("🔄 Refresh", key="refresh_overview"):
            st.session_state.pop(cache_key, None)
            st.rerun()
        return

    df = pd.DataFrame(rows)
    df = df[df["status"] != "On Leave"]
    df["actual_km"]    = pd.to_numeric(df["actual_km"],    errors="coerce").fillna(0)
    df["scheduled_km"] = pd.to_numeric(df["scheduled_km"], errors="coerce").fillna(0)
    df["income"]       = pd.to_numeric(df["income"],       errors="coerce").fillna(0)
    df["diesel"]       = pd.to_numeric(df["diesel"],       errors="coerce").fillna(0)
    df["date"]         = pd.to_datetime(df["date"])

    summary = df.groupby("bus_number").agg(
        Actual_KM   =("actual_km",    "sum"),
        Scheduled_KM=("scheduled_km", "sum"),
        Income      =("income",       "sum"),
        Diesel      =("diesel",       "sum"),
        Days        =("date",         "count"),
    ).reset_index().rename(columns={"bus_number": "Bus"})

    # ── Summary cards ──
    card_cols = st.columns(len(summary))
    for i, (_, row) in enumerate(summary.iterrows()):
        efficiency = round((row["Actual_KM"] / row["Scheduled_KM"] * 100), 1) \
            if row["Scheduled_KM"] > 0 else 0
        with card_cols[i]:
            st.markdown(f"""
            <div style='background:#14A085;border-radius:12px;padding:16px;
                        text-align:center;border:1px solid rgba(255,255,255,0.2);'>
                <div style='font-size:1.1rem;font-weight:600;color:white;
                            margin-bottom:8px;'>🚌 {row["Bus"]}</div>
                <div style='color:#d0f5ee;font-size:0.8rem;'>Actual KM</div>
                <div style='color:white;font-size:1.3rem;font-weight:700;'>
                    {int(row["Actual_KM"]):,}</div>
                <div style='color:#d0f5ee;font-size:0.75rem;margin-top:4px;'>
                    Efficiency: {efficiency}%</div>
                <div style='color:#d0f5ee;font-size:0.75rem;margin-top:4px;'>
                    {int(row["Days"])} days</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 3 Charts ──
    tab1, tab2, tab3 = st.tabs([
        "📈 Daily KM Trend",
        "📊 Scheduled vs Actual KM",
        "🥧 Driver Duty Distribution",
    ])

    # Tab 1 — Line chart: Date vs Actual KM per bus
    with tab1:
        pivot = df.pivot_table(
            index="date", columns="bus_number", values="actual_km", aggfunc="sum"
        ).fillna(0)
        pivot.index = pivot.index.strftime("%d %b")
        st.line_chart(pivot, use_container_width=True)
        st.caption("Har bus ki daily Actual KM trend")

    # Tab 2 — Grouped bar: Scheduled KM vs Actual KM per bus
    with tab2:
        grouped = summary[["Bus", "Scheduled_KM", "Actual_KM"]].set_index("Bus")
        grouped.columns = ["Scheduled KM", "Actual KM"]
        st.bar_chart(grouped, use_container_width=True)
        st.caption("Scheduled KM vs Actual KM — bus wise comparison")

    # Tab 3 — Pie chart: Driver wise duty days
    with tab3:
        driver_days = df.groupby("driver_name")["date"].count().reset_index()
        driver_days.columns = ["Driver", "Days"]
        driver_days = driver_days.sort_values("Days", ascending=False)

        # Streamlit mein pie chart nahi hai — plotly use karo
        try:
            import plotly.express as px
            fig = px.pie(
                driver_days,
                names="Driver",
                values="Days",
                color_discrete_sequence=px.colors.qualitative.Set3,
                hole=0.3,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white",
                margin=dict(t=20, b=20, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            # Plotly nahi hai toh bar chart fallback
            st.bar_chart(driver_days.set_index("Driver"), use_container_width=True)
        st.caption("Driver wise duty days distribution")

    if st.button("🔄 Refresh Overview", key="refresh_overview"):
        st.session_state.pop(cache_key, None)
        st.rerun()
