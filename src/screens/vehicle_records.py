import calendar
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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


def _plotly_dark(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        margin=dict(t=30, b=20, l=20, r=20),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


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
                    bus, type=btn_type, key=f"btn_v_{bus}",
                    width='stretch', icon=':material/bus_railway:', icon_position='right'
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
    period_label = f"{date.today().strftime('%B')} ({period})"

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
    df = df[df["status"] != "On Leave"].copy()
    df["actual_km"]    = pd.to_numeric(df["actual_km"],    errors="coerce").fillna(0)
    df["scheduled_km"] = pd.to_numeric(df["scheduled_km"], errors="coerce").fillna(0)
    df["income"]       = pd.to_numeric(df["income"],       errors="coerce").fillna(0)
    df["diesel"]       = pd.to_numeric(df["diesel"],       errors="coerce").fillna(0)
    df["date"]         = pd.to_datetime(df["date"])
    df["date_str"]     = df["date"].dt.strftime("%d %b")

    # ── Feature Engineering ──
    df["efficiency_pct"] = (df["actual_km"] / df["scheduled_km"].replace(0, float("nan")) * 100).round(1)
    df["achieved"]       = df["actual_km"] >= df["scheduled_km"]
    df["income_per_km"]  = (df["income"] / df["actual_km"].replace(0, float("nan"))).round(2)
    df["diesel_per_km"]  = (df["diesel"] / df["actual_km"].replace(0, float("nan"))).round(3)
    df["km_per_litre"]   = (df["actual_km"] / df["diesel"].replace(0, float("nan"))).round(2)

    summary = df.groupby("bus_number").agg(
        Actual_KM      =("actual_km",      "sum"),
        Scheduled_KM   =("scheduled_km",   "sum"),
        Income         =("income",         "sum"),
        Diesel         =("diesel",         "sum"),
        Days           =("date",           "count"),
        Achieved_Days  =("achieved",       "sum"),
        Avg_Efficiency =("efficiency_pct", "mean"),
        Best_KM_Day    =("actual_km",      "max"),
        Worst_KM_Day   =("actual_km",      "min"),
    ).reset_index().rename(columns={"bus_number": "Bus"})
    summary["Consistency_%"] = (summary["Achieved_Days"] / summary["Days"] * 100).round(1)
    summary["Avg_Efficiency"] = summary["Avg_Efficiency"].round(1)

    # ── Summary Cards ──
    card_cols = st.columns(len(summary))
    for i, (_, row) in enumerate(summary.iterrows()):
        with card_cols[i]:
            st.markdown(f"""
            <div style='background:#14A085;border-radius:12px;padding:16px;
                        text-align:center;border:1px solid rgba(255,255,255,0.2);'>
                <div style='font-size:1.1rem;font-weight:600;color:white;margin-bottom:8px;'>
                    🚌 {row["Bus"]}</div>
                <div style='color:#d0f5ee;font-size:0.78rem;'>Actual KM</div>
                <div style='color:white;font-size:1.3rem;font-weight:700;'>{int(row["Actual_KM"]):,}</div>
                <div style='color:#d0f5ee;font-size:0.78rem;margin-top:4px;'>Efficiency</div>
                <div style='color:#FFD700;font-size:1rem;font-weight:600;'>{row["Avg_Efficiency"]}%</div>
                <div style='color:#d0f5ee;font-size:0.75rem;margin-top:4px;'>
                    Consistency: {row["Consistency_%"]}% · {int(row["Days"])} days</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Daily KM Trend",
        "📊 Scheduled vs Actual",
        "🎯 KM Efficiency",
        "🥧 Driver Distribution",
        "👤 Driver Performance",
        "⛽ Diesel & Income",
    ])

    # ── Tab 1: Daily KM Trend (line chart per bus) ──
    with tab1:
        pivot = df.pivot_table(
            index="date_str", columns="bus_number",
            values="actual_km", aggfunc="sum"
        ).fillna(0)
        fig = go.Figure()
        colors = ["#14A085", "#7B8CFF", "#FFB347", "#FF5252"]
        for i, col in enumerate(pivot.columns):
            fig.add_trace(go.Scatter(
                x=pivot.index, y=pivot[col],
                mode="lines+markers", name=col,
                line=dict(color=colors[i % len(colors)], width=2),
                marker=dict(size=6),
            ))
        fig.update_layout(
            xaxis_title="Date", yaxis_title="Actual KM",
            hovermode="x unified",
        )
        st.plotly_chart(_plotly_dark(fig), use_container_width=True)
        st.caption("Har bus ki daily Actual KM trend — dips aur peaks")

    # ── Tab 2: Scheduled vs Actual KM (grouped bar) ──
    with tab2:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Scheduled KM", x=summary["Bus"],
            y=summary["Scheduled_KM"], marker_color="#7B8CFF"
        ))
        fig.add_trace(go.Bar(
            name="Actual KM", x=summary["Bus"],
            y=summary["Actual_KM"], marker_color="#14A085"
        ))
        fig.update_layout(barmode="group", xaxis_title="Bus", yaxis_title="KM")
        st.plotly_chart(_plotly_dark(fig), use_container_width=True)
        st.caption("Scheduled KM vs Actual KM — gap = efficiency loss")

    # ── Tab 3: KM Efficiency % per bus over time ──
    with tab3:
        eff_pivot = df.pivot_table(
            index="date_str", columns="bus_number",
            values="efficiency_pct", aggfunc="mean"
        ).fillna(0)
        fig = go.Figure()
        for i, col in enumerate(eff_pivot.columns):
            fig.add_trace(go.Scatter(
                x=eff_pivot.index, y=eff_pivot[col],
                mode="lines+markers", name=col,
                line=dict(color=colors[i % len(colors)], width=2),
            ))
        fig.add_hline(y=100, line_dash="dash", line_color="gray",
                      annotation_text="100% target")
        fig.update_layout(xaxis_title="Date", yaxis_title="Efficiency %")
        st.plotly_chart(_plotly_dark(fig), use_container_width=True)

        # Best/Worst day per bus
        st.markdown("**Best & Worst Day per Bus:**")
        bw_cols = st.columns(len(summary))
        for i, (_, row) in enumerate(summary.iterrows()):
            with bw_cols[i]:
                st.markdown(f"""
                <div style='background:#1e1e3a;border-radius:8px;padding:10px;text-align:center;'>
                    <b>🚌 {row["Bus"]}</b><br>
                    <span style='color:#69F0AE;'>Best: {int(row["Best_KM_Day"])} km</span><br>
                    <span style='color:#FF5252;'>Worst: {int(row["Worst_KM_Day"])} km</span>
                </div>
                """, unsafe_allow_html=True)

    # ── Tab 4: Driver Duty Distribution per vehicle (donut) ──
    with tab4:
        donut_cols = st.columns(len(bus_list))
        for i, bus in enumerate(bus_list):
            bus_df = df[df["bus_number"] == bus]
            driver_days = (
    bus_df.assign(
        driver_name=bus_df["driver_name"].str.lower().str.strip()
    ).groupby("driver_name")["date"].count().reset_index())
            driver_days.columns = ["Driver", "Days"]
            with donut_cols[i]:
                st.markdown(f"**🚌 {bus}**")
                fig = px.pie(
                    driver_days, names="Driver", values="Days",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(_plotly_dark(fig), use_container_width=True)
        st.caption("Har bus mein driver duty distribution")

    # ── Tab 5: Driver Performance ──
    with tab5:
        driver_perf = (df.assign( driver_name=df["driver_name"].str.strip().str.lower())
            .groupby("driver_name")
            .agg(
                Total_KM=("actual_km", "sum"),
                Avg_KM_Day=("actual_km", "mean"),
                Days=("date", "count"),
                Avg_Efficiency=("efficiency_pct", "mean"),
                Income=("income", "sum"),
            )
            .reset_index()
            .rename(columns={"driver_name": "Driver"})
                )
        driver_perf["Avg_KM_Day"]    = driver_perf["Avg_KM_Day"].round(1)
        driver_perf["Avg_Efficiency"] = driver_perf["Avg_Efficiency"].round(1)
        driver_perf = driver_perf.sort_values("Total_KM", ascending=False)
        driver_perf.insert(0, "Rank", range(1, len(driver_perf) + 1))

        st.dataframe(driver_perf, use_container_width=True, hide_index=True)

        # Driver KM bar chart
        fig = px.bar(
            driver_perf, x="Driver", y="Total_KM",
            color="Total_KM", color_continuous_scale="teal",
            text="Total_KM",
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig.update_layout(xaxis_title="Driver", yaxis_title="Total KM",
                          coloraxis_showscale=False)
        st.plotly_chart(_plotly_dark(fig), use_container_width=True)
        st.caption("Driver wise total KM — sabse upar = best performer")

    # ── Tab 6: Diesel & Income Analytics ──
    with tab6:
        has_diesel = df["diesel"].sum() > 0
        has_income = df["income"].sum() > 0

        if not has_diesel and not has_income:
            st.info("Diesel aur Income data abhi fill nahi hai — vehicle records mein add karo.")
        else:
            if has_diesel:
                st.markdown("**⛽ Diesel — Bus wise**")
                fig = px.bar(
                    summary, x="Bus", y="Diesel",
                    color="Bus", text="Diesel",
                    color_discrete_sequence=["#FFB347", "#FF8C00", "#FFA500", "#FF6347"],
                )
                fig.update_traces(texttemplate="%{text:.1f} L", textposition="outside")
                fig.update_layout(showlegend=False, yaxis_title="Diesel (L)")
                st.plotly_chart(_plotly_dark(fig), use_container_width=True)

                # KM per litre
                mileage = df[df["diesel"] > 0].groupby("bus_number").apply(
                    lambda x: (x["actual_km"].sum() / x["diesel"].sum()).round(2)
                ).reset_index()
                mileage.columns = ["Bus", "KM per Litre"]
                st.markdown("**Mileage (KM/L) per Bus:**")
                st.dataframe(mileage, use_container_width=True, hide_index=True)

            if has_income:
                st.markdown("**💰 Income — Bus wise**")
                fig = px.bar(
                    summary, x="Bus", y="Income",
                    color="Bus", text="Income",
                    color_discrete_sequence=["#14A085", "#7B8CFF", "#FF5252", "#FFB347"],
                )
                fig.update_traces(texttemplate="₹%{text:,}", textposition="outside")
                fig.update_layout(showlegend=False, yaxis_title="Income (₹)")
                st.plotly_chart(_plotly_dark(fig), use_container_width=True)

            if has_diesel and has_income:
                st.markdown("**💰 Income vs ⛽ Diesel Cost (@ ₹90/L est.):**")
                summary["Est_Diesel_Cost"] = (summary["Diesel"] * 90).round(0)
                summary["Net"]             = summary["Income"] - summary["Est_Diesel_Cost"]
                fig = go.Figure()
                fig.add_trace(go.Bar(name="Income",         x=summary["Bus"], y=summary["Income"],         marker_color="#14A085"))
                fig.add_trace(go.Bar(name="Est Diesel Cost",x=summary["Bus"], y=summary["Est_Diesel_Cost"],marker_color="#FF5252"))
                fig.update_layout(barmode="group", yaxis_title="₹")
                st.plotly_chart(_plotly_dark(fig), use_container_width=True)

    if st.button("🔄 Refresh Overview", key="refresh_overview"):
        st.session_state.pop(cache_key, None)
        st.rerun()
