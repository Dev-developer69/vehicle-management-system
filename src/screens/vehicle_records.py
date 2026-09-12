import calendar
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from src.ui.home_base_layout import home_layout
from src.database.auth import get_accessible_vehicles
from src.database.config import supabase
from src.database.db import (
    get_diesel_rate_payment, get_km_combines, get_diesel_records_raw,
    get_income_records_raw, get_dated_diesel_records_raw, get_maintenance_records,
    get_vehicle_payment_config, get_fuel_fills,
    get_conductor_income_records_raw, get_dated_income_records_raw,
)
from src.ml.mileage_anomaly import (
    compute_mileage_baseline, mileage_zscore, mileage_alert_status, baseline_summary_rows,
    FALLBACK_MIN_MILEAGE, MIN_HISTORY_FOR_ML,
)
from src.ml.driver_clustering import cluster_drivers
from src.ml.income_anomaly import (
    compute_income_baseline, income_zscore, income_alert_status, income_baseline_summary_rows,
)
from src.ml.diesel_forecast import forecast_diesel, forecast_summary_rows
from src.ml.multivariate_anomaly import detect_multivariate_anomalies
from src.ml.health_score import compute_fleet_health
from src.ml.income_forecast import forecast_income, income_forecast_summary_rows
from src.ml.conductor_income_trend import compute_conductor_income_trends, conductor_income_trend_rows
from src.ml.profitability_segmentation import segment_bus_profitability
from src.ml.festival_calendar import get_upcoming_festivals, is_festival_window
from src.ml.festival_aware_income import (
    compute_income_baseline_festival_aware, income_alert_status_festival_aware,
    estimate_festival_income_multiplier, conductor_festival_performance,
)
from src.ui.excel_format import shift_period_back, _get_date_range

VEHICLE_MAP = {
    "7389": "page_7389",
    "2350": "page_2350",
    "0303": "page_0303",
    "3131": "page_3131",
    "AT7389": "page_AT7389",
}

# FALLBACK_MIN_MILEAGE aur MIN_HISTORY_FOR_ML ab src/ml/mileage_anomaly.py se import hote hain
DIESEL_PRICE_PER_L = 95.69

COLORS = ["#14A085", "#7B8CFF", "#FFB347", "#FF5252", "#00D4FF", "#FF69B4"]


SYSTEM_PROMPT = (
    "You are a strict fleet operations analyst for an Indian diesel bus transport company. "
    "STEP 1 DATA VALIDATION always do this first: "
    "Scan all records for logical inconsistencies and flag them inline, do NOT exclude them from analysis. "
    "Flag these patterns with a warning note next to the bus name: "
    "Income > 0 and Diesel = 0 means add note Diesel entry missing verify fuel records. "
    "Actual KM > 0 and Diesel = 0 means add note diesel bus cannot run without fuel data error. "
    "Income = 0 but Actual KM > 0 means add note Revenue data may be missing. "
    "Diesel > 0 but Actual KM = 0 means add note Fuel recorded but vehicle did not operate. "
    "Net > Income means add note Calculation error verify. "
    "Show these as a Data Quality section first, then include ALL buses in performance analysis with warning tags. "
    "STEP 2 PERFORMANCE ANALYSIS — BANNED PATTERN: "
    "Never write an insight that just names the highest or lowest raw number in the data "
    "(e.g. 'Bus X has highest payment Rs Y') — that is visible on the table already and is NOT an insight, "
    "it will be REJECTED. Every bullet must do at least one of: "
    "(a) compare a bus's ratio (diesel cost as %% of payment, income per km, net margin %%) against the FLEET AVERAGE "
    "of that same ratio and state the deviation, "
    "(b) connect two different signals together to explain WHY something is happening — e.g. a low mileage z-score "
    "combined with a high diesel cost, or a declining income trend combined with a specific conductor/driver, "
    "(c) compare this period's number against the previous period for the same bus if previous-period data is given, "
    "(d) flag a bus that looks fine on totals but has a bad ratio (e.g. high payment but even higher diesel-cost ratio "
    "than the fleet average, meaning the size of the number is hiding a margin problem). "
    "If two buses have similar totals but different ratios, that gap IS the insight — surface it. "
    "STEP 3: include all buses, tag inconsistent ones with a warning tag like [verify diesel data] or [revenue missing]. "
    "ABSOLUTE RULES: "
    "1. Use ONLY the exact numbers from the data never round estimate or invent. "
    "2. Copy rupee and KM values exactly as given. "
    "3. Plain text only no markdown no bold no asterisks. "
    "4. Follow the exact output format in the prompt. "
    "5. Max 2 bullets per section each under 25 words. "
    "6. A diesel bus CANNOT run without diesel always flag Diesel=0 with KM>0 or Income>0 as data error. "
    "7. Every performance bullet (Strengths/Opportunities/Critical) must include a ratio, deviation, or comparison — "
    "never a single standalone total."
)


def _call_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=300,
        temperature=0.1,  # low temp = less hallucination
    )
    return chat.choices[0].message.content.strip()


def _call_claude_api(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _supabase_get_insight(cache_key: str) -> str | None:
    """Fetch insight from Supabase ai_insights table."""
    try:
        res = supabase.table("ai_insights").select("insight").eq("cache_key", cache_key).single().execute()
        return res.data["insight"] if res.data else None
    except Exception:
        return None


def _supabase_save_insight(cache_key: str, insight: str, provider: str) -> None:
    """Upsert insight into Supabase ai_insights table."""
    try:
        supabase.table("ai_insights").upsert({
            "cache_key": cache_key,
            "insight":   insight,
            "provider":  provider,
            "updated_at": "now()",
        }, on_conflict="cache_key").execute()
    except Exception:
        pass  # silently fail — session cache still works


def _show_insight(prompt: str, key: str = ""):
    """Button-based lazy load — result stored in Supabase + session cache."""
    cache_key = f"insight_{abs(hash(prompt[:100]))}"
    provider  = st.session_state.get("ai_provider", "Groq")

    def _render(insight: str, regen_key: str):
        st.markdown(f"""
        <div style='background:rgba(123,140,255,0.12);border-left:3px solid #7B8CFF;
                    border-radius:6px;padding:10px 14px;margin-top:6px;
                    font-size:0.85rem;color:#d0eaff;white-space:pre-line;'>{insight}
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔄 Regenerate", key=regen_key, help="Fetch fresh insight from AI"):
            st.session_state.pop(cache_key, None)
            # Delete from Supabase so fresh insight is fetched
            try:
                supabase.table("ai_insights").delete().eq("cache_key", cache_key).execute()
            except Exception:
                pass
            st.rerun()

    # 1. Check session cache first (fastest)
    if cache_key in st.session_state:
        _render(st.session_state[cache_key], f"regen_{cache_key}")
        return

    # 2. Check Supabase (persistent across sessions)
    with st.spinner("Loading saved insight..."):
        saved = _supabase_get_insight(cache_key)
    if saved:
        st.session_state[cache_key] = saved
        _render(saved, f"regen_{cache_key}")
        return

    # 3. Show generate button — no saved insight found
    icon = "🟢 Groq" if provider == "Groq" else "🔵 Claude"
    if st.button(f"🤖 Generate AI Insight ({icon})", key=f"gen_{cache_key}", type="secondary"):
        with st.spinner("Analyzing..."):
            try:
                result = _call_groq(prompt) if provider == "Groq" else _call_claude_api(prompt)
                # Save to session + Supabase
                st.session_state[cache_key] = result
                _supabase_save_insight(cache_key, result, provider)
                st.rerun()
            except KeyError as e:
                st.warning(f"⚠️ API key missing: {e}")
            except Exception as e:
                st.error(f"❌ {provider} error: {e}")



def _compute_bus_final_payment(bus_number: str, total_income: float, total_actual_km: float) -> float:
    """Vehicle Records ke 'Payment Summary' jaisa hi calculation — is bus ke
    saved payment config (Standard ya IPKM Slab) ke hisaab se, is period ke
    Total Income aur Total Actual KM se Final Payment nikalta hai."""
    cfg = get_vehicle_payment_config(bus_number)
    PERIOD_TAX = 11700
    if cfg["method"] == "standard":
        raw_payment = total_income - (total_actual_km * cfg["rate"]) - PERIOD_TAX
        tax_pct = 0.01
    else:
        ipkm = (total_income - PERIOD_TAX) / total_actual_km if total_actual_km > 0 else 0
        if ipkm < cfg["ipkm_threshold"]:
            raw_payment = (ipkm - cfg["ipkm_deduction"]) * total_actual_km
        else:
            raw_payment = (cfg["ipkm_threshold"] - cfg["ipkm_deduction"]) * total_actual_km
        tax_pct = 0.02  # ✅ IPKM Slab wale vehicles ke liye 2% tax (Standard = 1%)
    return raw_payment - (raw_payment * tax_pct) - cfg["final_deduction"]


def _plotly_dark(fig):
    fig.update_layout(
        paper_bgcolor="#0d2626",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white", size=11),
        margin=dict(t=30, b=10, l=10, r=10),
        autosize=True,
        legend=dict(
            bgcolor="rgba(0,0,0,0)", font=dict(size=10),
            orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5,
        ),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.08)", type="category",
            tickangle=-40, tickfont=dict(size=10), automargin=True,
        ),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", tickfont=dict(size=10), automargin=True),
    )
    return fig


def _render_chart(fig, key: str):
    """Mobile-friendly plotly render — mode-bar chhupao, responsive banao."""
    st.plotly_chart(
        fig, width='stretch', key=key,
        config={"displayModeBar": False, "responsive": True},
    )


def _maintenance_overdue_days(bus_number: str) -> int:
    """Health Score ke liye — bus ka koi bhi service kitne din se overdue hai
    (sirf Next Due Date based check, lightweight — poora KM-based check
    src/ml/maintenance_predictor.py + Maintenance Manager page me hota hai)."""
    try:
        records_df = get_maintenance_records(bus_number)
    except Exception:
        return 0
    if records_df.empty:
        return 0
    latest_per_type = records_df.groupby("Service Type")["Date"].max().to_dict()
    max_overdue = 0
    for _, r in records_df.iterrows():
        if r["Date"] != latest_per_type[r["Service Type"]]:
            continue
        if r["Next Due Date"]:
            try:
                nd = pd.to_datetime(r["Next Due Date"]).date()
                overdue = (date.today() - nd).days
                max_overdue = max(max_overdue, overdue)
            except (ValueError, TypeError):
                pass
    return max_overdue


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
    st.markdown("""
        <style>
            .stApp { background: #1B3B6F !important; color: #F0F0F0 !important; }
        </style>
    """, unsafe_allow_html=True)

    accessible = get_accessible_vehicles()
    visible_vehicles = [bus for bus in VEHICLE_MAP.keys() if bus in accessible]

    if not visible_vehicles:
        st.warning("⚠️ Aapko kisi bhi vehicle ka access nahi diya gaya. Admin se contact karo.")
    else:
        n = len(visible_vehicles)
        i = 0
        while i < n:
            if i == n - 1:
                # akela bacha last vehicle — center me dikhao, purple (Home page jaisa)
                _, ccenter, _ = st.columns([1, 2, 1])
                bus = visible_vehicles[i]
                with ccenter:
                    if st.button(
                        bus, type='primary', key=f"btn_v_{bus}",
                        width='stretch', icon=':material/bus_railway:', icon_position='right'
                    ):
                        st.session_state['login_state'] = VEHICLE_MAP[bus]
                        st.rerun()
                i += 1
            else:
                cols = st.columns(2)
                for j in range(2):
                    bus = visible_vehicles[i + j]
                    with cols[j]:
                        btn_type = 'secondary' if (i + j) < 2 else 'tertiary'
                        if st.button(
                            bus, type=btn_type, key=f"btn_v_{bus}",
                            width='stretch', icon=':material/bus_railway:', icon_position='right'
                        ):
                            st.session_state['login_state'] = VEHICLE_MAP[bus]
                            st.rerun()
                i += 2

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

    sel_col1, sel_col2, sel_col3 = st.columns([2, 2, 1])
    with sel_col1:
        sel_month = st.selectbox(
            "Month", options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda x: date(2000, x, 1).strftime("%B"),
            key="qo_month"
        )
    with sel_col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        sel_period = st.radio(
            "Period", ["1-15", "16-31"],
            index=0 if default_half == "1-15" else 1,
            horizontal=True, key="qo_period"
        )
    with sel_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        load_clicked = st.button("🔄 Load", key="qo_load", width='stretch')

    year = date.today().year
    raw_start, raw_end = _get_date_range(year, sel_month, sel_period)
    start, end = raw_start.date(), raw_end.date()
    period_label = f"{date(2000, sel_month, 1).strftime('%B')} ({sel_period})"

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:10px;margin-bottom:0.5rem;'>
        <span style='font-size:1.5rem;'>📊</span>
        <span style='font-size:1.2rem;font-weight:600;'>Quick Overview</span>
        <span style='font-size:0.85rem;color:#aaa;margin-left:8px;'>{period_label}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 🎉 Upcoming Festival Banner — ek hi jagah, har tab me repeat nahi ──
    upcoming = get_upcoming_festivals(days_ahead=20)
    if upcoming:
        next_fest = upcoming[0]
        st.markdown(f"""
        <div style='background:linear-gradient(90deg,#FFB347,#FF8C42);border-radius:10px;
                    padding:10px 16px;margin-bottom:10px;color:#1a1a1a;font-weight:600;'>
            🎉 {next_fest['name']} in {next_fest['days_away']} din ({next_fest['date'].strftime('%d %b')})
            — income surge expect karo, staffing/schedule pehle se plan kar lo.
        </div>
        """, unsafe_allow_html=True)

    cache_key = f"overview_{start}_{end}"

    if cache_key not in st.session_state or load_clicked:
        cols_sel = "bus_number, date, driver_name, conductor_name, actual_km, scheduled_km, income, gross_income, diesel, diesel_km, status, next_period"
        prev_start, prev_end = shift_period_back(year, sel_month, sel_period)

        normal_res = supabase.table("vehicle_records") \
            .select(cols_sel) \
            .in_("bus_number", bus_list) \
            .gte("date", str(start)) \
            .lte("date", str(end)) \
            .execute()
        normal_rows = [r for r in (normal_res.data or []) if not r.get("next_period")]

        shifted_res = supabase.table("vehicle_records") \
            .select(cols_sel) \
            .in_("bus_number", bus_list) \
            .gte("date", str(prev_start)) \
            .lte("date", str(prev_end)) \
            .eq("next_period", True) \
            .execute()
        shifted_rows = shifted_res.data or []
        st.session_state[cache_key] = normal_rows + shifted_rows

    rows = st.session_state[cache_key]

    if not rows:
        st.info("Is period mein koi record nahi mila.")
        if st.button("🔄 Refresh", key="refresh_overview"):
            st.session_state.pop(cache_key, None)
            st.rerun()
        return

    df_all = pd.DataFrame(rows)
    # ── df_all: On Leave dates INCLUDED — sirf Daily KM Trend chart ke liye,
    # taaki us din bus ka Actual KM asal me 0 dikhaya jaaye (leave ke din
    # scheduled_km/actual_km save hote waqt already 0 hote hain), na ki
    # graph se poori tarah gayab ho ke line ko interpolate/smooth kar de. ──
    df_all["actual_km"]    = pd.to_numeric(df_all["actual_km"],    errors="coerce").fillna(0)
    df_all["scheduled_km"] = pd.to_numeric(df_all["scheduled_km"], errors="coerce").fillna(0)
    df_all["date"]         = pd.to_datetime(df_all["date"])
    df_all["bus_number"]   = df_all["bus_number"].astype(str)
    df_all["days_count"]   = 1
    df_all["days_label"]   = df_all["date"].dt.strftime("%d %b")

    df = df_all[df_all["status"] != "On Leave"].copy()
    df["income"]         = pd.to_numeric(df["income"],       errors="coerce").fillna(0)
    df["diesel"]         = pd.to_numeric(df["diesel"],       errors="coerce").fillna(0)
    df["diesel_km"]      = pd.to_numeric(df["diesel_km"] if "diesel_km" in df.columns else 0, errors="coerce").fillna(0)
    df["conductor_name"] = df["conductor_name"].fillna("") if "conductor_name" in df.columns else ""

    # ── Combine-merge logic Quick Overview me DISABLED — har date apni raw
    # actual/scheduled KM ke saath alag row rehti hai, taaki "Days" count
    # asal calendar dates dikhaye aur Efficiency bhi per-din KM se nikle
    # (Saved Records table ka "Kayi Din Ka KM Combine Karo" feature isse
    # unaffected hai — wahan waisa hi combine-merge dikhega). ──
    df_by_day = df.copy()

    df_by_day["date_str"] = df_by_day["date"].dt.strftime("%d %b")
    df_by_day["efficiency_pct"] = (df_by_day["actual_km"] / df_by_day["scheduled_km"].replace(0, float("nan")) * 100).round(1)
    df["date_str"]       = df["date"].dt.strftime("%d %b")

    df["efficiency_pct"] = (df["actual_km"] / df["scheduled_km"].replace(0, float("nan")) * 100).round(1)
    df["achieved"]       = df["actual_km"] >= df["scheduled_km"]
    df["income_per_km"]  = (df["income"] / df["actual_km"].replace(0, float("nan"))).round(2)
    df["diesel_per_km"]  = (df["diesel"] / df["actual_km"].replace(0, float("nan"))).round(3)
    df["km_per_litre"]   = (df["diesel_km"] / df["diesel"].replace(0, float("nan"))).round(2)

    # ── Mileage anomaly detection — src/ml/mileage_anomaly.py karta hai, yahan sirf call ──
    mileage_baseline = compute_mileage_baseline(
        get_diesel_records_raw(list(df["bus_number"].unique()))
    )

    df["mileage_zscore"] = df.apply(
        lambda r: mileage_zscore(r["bus_number"], r["km_per_litre"], mileage_baseline), axis=1
    )
    df["alert_status"] = df.apply(
        lambda r: mileage_alert_status(
            r["bus_number"], r["actual_km"], r["diesel"], r["km_per_litre"], mileage_baseline
        ), axis=1
    )

    # ── Income anomaly detection — src/ml/income_anomaly.py karta hai ──
    income_baseline = compute_income_baseline(
        get_income_records_raw(list(df["bus_number"].unique()))
    )
    df["income_zscore"] = df.apply(
        lambda r: income_zscore(r["bus_number"], r["income_per_km"], income_baseline), axis=1
    )

    summary = df.groupby("bus_number").agg(
        Actual_KM     =("actual_km",      "sum"),
        Scheduled_KM  =("scheduled_km",   "sum"),
        Income        =("income",         "sum"),
        Diesel        =("diesel",         "sum"),
        Diesel_KM     =("diesel_km",      "sum"),
        Days          =("date",           "count"),
        Achieved_Days =("achieved",       "sum"),
        Avg_Efficiency=("efficiency_pct", "mean"),
        Best_KM_Day   =("actual_km",      "max"),
        Worst_KM_Day  =("actual_km",      "min"),
    ).reset_index().rename(columns={"bus_number": "Bus"})
    summary["Bus"]            = summary["Bus"].astype(str)
    summary["Consistency_%"]  = (summary["Achieved_Days"] / summary["Days"] * 100).round(1)
    summary["Avg_Efficiency"] = summary["Avg_Efficiency"].round(1)

    bus_rates = {}
    for bus in summary["Bus"].tolist():
        rate_data = get_diesel_rate_payment(bus, sel_month, sel_period)
        bus_rates[bus] = rate_data["rate"]
    summary["Diesel_Rate"] = summary["Bus"].map(bus_rates)

    # ✅ Diesel figures ab vehicle_records.diesel (legacy/synced field) se nahi —
    # seedhe "Diesel/CNG View" wale fuel_fills table se (jahan asal refuel
    # entries record hoti hain), taaki dono jagah exact same numbers dikhein.
    fuel_diesel, fuel_cost = {}, {}
    for bus in summary["Bus"].tolist():
        fills = get_fuel_fills(bus, str(start), str(end))
        fuel_diesel[bus] = float(fills["Quantity"].sum()) if not fills.empty else 0.0
        fuel_cost[bus]   = float(fills["Amount"].sum())   if not fills.empty else 0.0
    summary["Diesel"]          = summary["Bus"].map(fuel_diesel).fillna(0.0)
    summary["Est_Diesel_Cost"] = summary["Bus"].map(fuel_cost).fillna(0.0).round(0)
    # ✅ Effective rate = actual total cost / actual total litres (fuel_fills se) —
    # sirf diesel data na hone par fallback default rate (diesel_details) dikhao
    summary["Diesel_Rate"] = summary.apply(
        lambda r: round(r["Est_Diesel_Cost"] / r["Diesel"], 2) if r["Diesel"] > 0 else bus_rates.get(r["Bus"], 0),
        axis=1,
    )

    # ✅ Payment ab raw "Income" se nahi — har bus ke saved Payment Config
    # (Standard/IPKM Slab + 1% tax + final fixed deduction) se calculate hota
    # hai, isi period ke Total Income aur Total Actual KM ka use karke.
    summary["Payment"] = summary.apply(
        lambda r: round(_compute_bus_final_payment(r["Bus"], r["Income"], r["Actual_KM"]), 0), axis=1
    )
    summary["Net"] = summary["Payment"] - summary["Est_Diesel_Cost"]

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

    bus_color_map = {bus: COLORS[i % len(COLORS)] for i, bus in enumerate(bus_list)}

    # ── Global AI provider toggle ──
    ai_col1, ai_col2 = st.columns([3, 1])
    with ai_col2:
        provider = st.radio(
            "🤖 AI Insights",
            ["Groq", "Claude"],
            index=0 if st.session_state.get("ai_provider", "Groq") == "Groq" else 1,
            horizontal=True,
            key="ai_provider_radio",
            help="Groq: free & fast | Claude: better quality (needs ANTHROPIC_API_KEY)"
        )
        st.session_state["ai_provider"] = provider


    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "📈 Daily KM Trend", "📊 Scheduled vs Actual", "🎯 KM Efficiency",
        "🥧 Driver Distribution", "👤 Driver Performance", "⛽ Diesel & Income",
        "🚨 Mileage Alert", "💰 Income per KM", "📋 Monthly Summary",
    ])

    with tab1:
        # ✅ df_all use karo — isme On Leave dates bhi shamil hain (Actual KM=0
        # ke saath), taaki graph pe woh din poori tarah gayab hone ke bajaye
        # sahi se "0" pe dip dikhaye, na ki line interpolate ho ke smooth dikhe.
        pivot = df_all.pivot_table(
            index="date", columns="bus_number",
            values="actual_km", aggfunc="sum"
        ).sort_index()
        pivot_sched = df_all.pivot_table(
            index="date", columns="bus_number",
            values="scheduled_km", aggfunc="sum"
        ).sort_index()
        pivot_days = df_all.pivot_table(
            index="date", columns="bus_number",
            values="days_count", aggfunc="sum"
        ).sort_index()
        pivot_labels = df_all.pivot_table(
            index="date", columns="bus_number",
            values="days_label", aggfunc="last"
        ).sort_index()

        fig = go.Figure()

        for i, col in enumerate(pivot.columns):
            color = bus_color_map.get(str(col), COLORS[i % len(COLORS)])
            series = pivot[col].dropna()
            if series.empty:
                continue
            sched_series = pivot_sched[col].reindex(series.index).fillna(0)
            days_series  = pivot_days[col].reindex(series.index).fillna(1)
            label_series = pivot_labels[col].reindex(series.index).fillna("")
            customdata   = list(zip(sched_series.values, days_series.values, label_series.values))

            # convert hex to rgba for soft fill
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            fill_color = f"rgba({r},{g},{b},0.12)"

            # Glowing gradient area under the line
            fig.add_trace(go.Scatter(
                x=series.index, y=series.values,
                mode="lines", name=col, legendgroup=col,
                line=dict(color=color, width=3, shape="spline", smoothing=0.4),
                fill="tozeroy", fillcolor=fill_color,
                customdata=customdata,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>%{x|%d %b}<br>"
                    "Actual: %{y:.0f} km<br>"
                    "Scheduled: %{customdata[0]:.0f} km<br>"
                    "Days: %{customdata[1]:.0f} (%{customdata[2]})<extra></extra>"
                ),
            ))
    
            # Markers on top (separate trace so fill doesn't clip them)
            fig.add_trace(go.Scatter(
                x=series.index, y=series.values,
                mode="markers", name=col, legendgroup=col, showlegend=False,
                marker=dict(size=7, color=color, line=dict(width=1.5, color="#0d2626")),
                hoverinfo="skip",
            ))
    
            # Highlight ring on the latest point
            fig.add_trace(go.Scatter(
                x=[series.index[-1]], y=[series.values[-1]],
                mode="markers", legendgroup=col, showlegend=False,
                marker=dict(size=16, color="rgba(0,0,0,0)",
                            line=dict(width=2, color=color)),
                hoverinfo="skip",
            ))
    
            # Callout on the best day
            best_idx = series.idxmax()
            fig.add_annotation(
                x=best_idx, y=series[best_idx],
                text=f"🏆 {int(series[best_idx])} km",
                showarrow=True, arrowhead=0, arrowcolor=color,
                ax=0, ay=-30,
                font=dict(size=11, color=color),
                bgcolor="rgba(13,38,38,0.85)", bordercolor=color, borderwidth=1, borderpad=4,
            )
    
        fig = _plotly_dark(fig)
        fig.update_layout(
            xaxis=dict(type="date", tickformat="%d %b", gridcolor="rgba(255,255,255,0.06)",
                       showspikes=True, spikemode="across", spikecolor="rgba(255,255,255,0.2)", spikethickness=1,
                       tickangle=-40, tickfont=dict(size=10), automargin=True),
            yaxis=dict(rangemode="tozero", gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=10)),
            xaxis_title="Date", yaxis_title="Actual KM",
            hovermode="x unified",
            height=420,
            margin=dict(t=20, b=10, l=10, r=10),
            legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5, font=dict(size=10)),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        _render_chart(fig, key="qo_chart_daily_trend")
        
        _show_insight(f"""
Period: {period_label}
Daily Actual KM per bus: {pivot.to_dict()}

Analyze this daily KM trend and respond in this exact format:
🟢 Strengths
• [which bus is most consistent and why]

🟠 Opportunities
• [buses with irregular or declining trend]

🔴 Critical Issues
• [buses with 0 KM days or sudden drops — name them]

💡 Recommendations
• [specific actions: route redistribution, maintenance check, etc.]

📈 Overall Status: Excellent / Good / Average / Poor
Keep each bullet to 1 line. Max 2 bullets per section.
""")

    with tab2:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Scheduled KM", x=summary["Bus"].tolist(), y=summary["Scheduled_KM"],
            marker_color="#7B8CFF",
            text=summary["Scheduled_KM"].astype(int), textposition="outside",
        ))
        fig.add_trace(go.Bar(
            name="Actual KM", x=summary["Bus"].tolist(), y=summary["Actual_KM"],
            marker_color="#14A085",
            text=summary["Actual_KM"].astype(int), textposition="outside",
        ))
        max_val = max(summary["Scheduled_KM"].max(), summary["Actual_KM"].max())
        fig.update_layout(
            barmode="group", xaxis_title="Bus", yaxis_title="KM",
            yaxis=dict(range=[0, max_val * 1.2], gridcolor="rgba(255,255,255,0.08)"),
            xaxis=dict(type="category", gridcolor="rgba(255,255,255,0.08)"),
            bargap=0.25, bargroupgap=0.05,
        )
        _render_chart(_plotly_dark(fig), key="qo_chart_sched_vs_actual")
        _show_insight(f"""
Scheduled KM: {summary.set_index('Bus')['Scheduled_KM'].to_dict()}
Actual KM: {summary.set_index('Bus')['Actual_KM'].to_dict()}

Analyze schedule adherence and respond in this exact format:
🟢 Strengths
• [bus meeting or exceeding schedule — name it]

🟠 Opportunities
• [bus consistently below schedule — name it and gap %]

🔴 Critical Issues
• [bus with largest gap or missed schedule — name it]

💡 Recommendations
• [specific fix: route change, driver reassignment, etc.]

📈 Overall Status: Excellent / Good / Average / Poor
Max 2 bullets per section. Be specific with numbers.
""")

    with tab3:
        eff_pivot = df.pivot_table(
            index="date", columns="bus_number",
            values="efficiency_pct", aggfunc="mean"
        ).sort_index()
    
        fig = go.Figure()
    
        for i, col in enumerate(eff_pivot.columns):
            color = bus_color_map.get(str(col), COLORS[i % len(COLORS)])
            series = eff_pivot[col].dropna()
            if series.empty:
                continue
    
            h = color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            fill_color = f"rgba({r},{g},{b},0.12)"
    
            # Glowing gradient area under the line
            fig.add_trace(go.Scatter(
                x=series.index, y=series.values,
                mode="lines", name=col, legendgroup=col,
                line=dict(color=color, width=3, shape="spline", smoothing=0.4),
                fill="tozeroy", fillcolor=fill_color,
                hovertemplate="<b>%{fullData.name}</b><br>%{x|%d %b}<br>%{y:.1f}%<extra></extra>",
            ))
    
            # Markers on top
            fig.add_trace(go.Scatter(
                x=series.index, y=series.values,
                mode="markers", name=col, legendgroup=col, showlegend=False,
                marker=dict(size=7, color=color, line=dict(width=1.5, color="#0d2626")),
                hoverinfo="skip",
            ))
    
            # Highlight ring on the latest point
            fig.add_trace(go.Scatter(
                x=[series.index[-1]], y=[series.values[-1]],
                mode="markers", legendgroup=col, showlegend=False,
                marker=dict(size=16, color="rgba(0,0,0,0)",
                            line=dict(width=2, color=color)),
                hoverinfo="skip",
            ))
    
            # Callout on the best (highest efficiency) day
            best_idx = series.idxmax()
            fig.add_annotation(
                x=best_idx, y=series[best_idx],
                text=f"🏆 {series[best_idx]:.1f}%",
                showarrow=True, arrowhead=0, arrowcolor=color,
                ax=0, ay=-30,
                font=dict(size=11, color=color),
                bgcolor="rgba(13,38,38,0.85)", bordercolor=color, borderwidth=1, borderpad=4,
            )
    
        fig.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="100% target")
    
        fig = _plotly_dark(fig)
        fig.update_layout(
            xaxis=dict(type="date", tickformat="%d %b", gridcolor="rgba(255,255,255,0.06)",
                       showspikes=True, spikemode="across", spikecolor="rgba(255,255,255,0.2)", spikethickness=1),
            yaxis=dict(rangemode="tozero", gridcolor="rgba(255,255,255,0.06)"),
            xaxis_title="Date", yaxis_title="Efficiency %",
            hovermode="x unified",
            height=480,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        _render_chart(fig, key="qo_chart_efficiency")
    
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
        _show_insight(f"""
    Avg KM Efficiency per bus: {eff_pivot.mean().to_dict()}
    Best/Worst day per bus: {summary[['Bus','Best_KM_Day','Worst_KM_Day']].to_dict('records')}
    
    Analyze efficiency and respond in this exact format:
    🟢 Strengths
    - [highest efficiency bus — name and % avg]
    
    🟠 Opportunities
    - [bus with large best/worst gap — name it]
    
    🔴 Critical Issues
    - [bus below 80% efficiency — name it, possible cause]
    
    💡 Recommendations
    - [maintenance check, load balancing, or route review]
    
    📈 Overall Status: Excellent / Good / Average / Poor
    Max 2 bullets per section. Plain text only.
    """)

    with tab4:
        donut_cols = st.columns(len(bus_list))
        for i, bus in enumerate(bus_list):
            bus_df = df_by_day[df_by_day["bus_number"] == bus]
            driver_days = (
                bus_df.assign(driver_name=bus_df["driver_name"].str.lower().str.strip())
                .groupby("driver_name")["date"].count().reset_index())
            driver_days.columns = ["Driver", "Days"]
            with donut_cols[i]:
                st.markdown(f"**🚌 {bus}**")
                fig = px.pie(driver_days, names="Driver", values="Days", hole=0.4,
                             color_discrete_sequence=["#14A085","#7B8CFF","#FFB347","#FF5252","#00D4FF","#FF69B4"])
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
                _render_chart(_plotly_dark(fig), key=f"qo_chart_donut_{bus}")
        st.caption("Har bus mein driver duty distribution")

    with tab5:
        driver_perf = (df_by_day.assign(driver_name=df_by_day["driver_name"].str.strip().str.lower())
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
        driver_perf["Avg_KM_Day"]     = driver_perf["Avg_KM_Day"].round(1)
        driver_perf["Avg_Efficiency"] = driver_perf["Avg_Efficiency"].round(1)
        driver_perf = driver_perf.sort_values("Total_KM", ascending=False)
        driver_perf.insert(0, "Rank", range(1, len(driver_perf) + 1))
        driver_perf = cluster_drivers(driver_perf)
        st.dataframe(driver_perf, width='stretch', hide_index=True)

        bar_colors = [COLORS[i % len(COLORS)] for i in range(len(driver_perf))]
        fig = go.Figure(go.Bar(
            x=driver_perf["Driver"], y=driver_perf["Total_KM"],
            marker_color=bar_colors,
            text=driver_perf["Total_KM"].astype(int), textposition="outside",
        ))
        max_val = driver_perf["Total_KM"].max()
        fig.update_layout(
            xaxis_title="Driver", yaxis_title="Total KM",
            xaxis=dict(type="category"),
            yaxis=dict(range=[0, max_val * 1.2], gridcolor="rgba(255,255,255,0.08)"),
        )
        _render_chart(_plotly_dark(fig), key="qo_chart_driver_perf")
        _show_insight(f"""
Driver performance data: {driver_perf[['Driver','Total_KM','Days','Avg_Efficiency']].to_dict('records')}

Analyze driver performance and respond in this exact format:
🟢 Strengths
• [top driver name, total KM, efficiency %]

🟠 Opportunities
• [driver with low utilization or inconsistency — name them]

🔴 Critical Issues
• [driver with 0 KM or very low efficiency — name them]

💡 Recommendations
• [training, route reassignment, or recognition suggestion]

📈 Overall Status: Excellent / Good / Average / Poor
Max 2 bullets per section. Mention driver names specifically.
""")

    with tab6:
        has_diesel = summary["Diesel"].sum() > 0
        has_income = df["income"].sum() > 0

        if not has_diesel and not has_income:
            st.info("Diesel aur Income data abhi fill nahi hai.")
        else:
            if has_diesel:
                st.markdown("**⛽ Diesel — Bus wise**")
                fig = go.Figure(go.Bar(
                    x=summary["Bus"].tolist(), y=summary["Diesel"],
                    marker_color=[bus_color_map.get(b, "#FFB347") for b in summary["Bus"]],
                    text=summary["Diesel"].round(1), textposition="outside",
                    texttemplate="%{text:.1f} L",
                ))
                max_d = summary["Diesel"].max()
                fig.update_layout(
                    showlegend=False, yaxis_title="Diesel (L)",
                    xaxis=dict(type="category"),
                    yaxis=dict(range=[0, max_d * 1.2], gridcolor="rgba(255,255,255,0.08)"),
                )
                _render_chart(_plotly_dark(fig), key="qo_chart_diesel_bus")

                mileage = df[df["diesel"] > 0].groupby("bus_number").apply(
                    lambda x: (x["diesel_km"].sum() / x["diesel"].sum()).round(2)
                    if x["diesel"].sum() > 0 else 0
                ).reset_index()
                mileage.columns = ["Bus", "KM per Litre"]
                st.markdown("**Mileage (KM/L) per Bus:**")
                st.dataframe(mileage, width='stretch', hide_index=True)

                # ── Diesel consumption forecast — agle 15 din ka expected diesel ──
                diesel_forecast = forecast_diesel(
                    get_dated_diesel_records_raw(list(df["bus_number"].unique())),
                    forecast_days=15,
                )
                if diesel_forecast:
                    st.markdown("**🔮 Agle 15 Din Ka Diesel Forecast:**")
                    DIESEL_RATE_PER_LITRE = 95.69
                    st.dataframe(
                        pd.DataFrame(forecast_summary_rows(diesel_forecast, rate_per_litre=DIESEL_RATE_PER_LITRE)),
                        width='stretch', hide_index=True,
                    )
                    total_forecast_litres = sum(f["forecast_litres"] for f in diesel_forecast.values())
                    st.caption(f"Total fleet forecast: ~{total_forecast_litres:.0f} L (~₹{total_forecast_litres * DIESEL_RATE_PER_LITRE:,.0f}) agle 15 din ke liye")

            if has_income:
                st.markdown("**💰 Payment — Bus wise**")
                fig = go.Figure(go.Bar(
                    x=summary["Bus"].tolist(), y=summary["Payment"],
                    marker_color=[bus_color_map.get(b, "#14A085") for b in summary["Bus"]],
                    text=summary["Payment"].astype(int), textposition="outside",
                    texttemplate="₹%{text:,}",
                ))
                max_i = summary["Payment"].max()
                fig.update_layout(
                    showlegend=False, yaxis_title="Payment (₹)",
                    xaxis=dict(type="category"),
                    yaxis=dict(range=[0, max_i * 1.2], gridcolor="rgba(255,255,255,0.08)"),
                )
                _render_chart(_plotly_dark(fig), key="qo_chart_income_bus")

                # ── Income forecast — agle 15 din ka expected revenue ──
                income_forecast = forecast_income(
                    get_dated_income_records_raw(list(df["bus_number"].unique())),
                    forecast_days=15,
                )
                if income_forecast:
                    st.markdown("**🔮 Agle 15 Din Ka Income Forecast:**")
                    _diesel_forecast_for_income = diesel_forecast if 'diesel_forecast' in locals() else {}
                    st.dataframe(
                        pd.DataFrame(income_forecast_summary_rows(income_forecast, _diesel_forecast_for_income, DIESEL_PRICE_PER_L)),
                        width='stretch', hide_index=True,
                    )
                    # Agar forecast window (agle 15 din) mein koi festival aata hai,
                    # multiplier se ek adjusted heads-up bhi dikha do
                    fest_soon = get_upcoming_festivals(days_ahead=15)
                    if fest_soon:
                        multipliers = estimate_festival_income_multiplier(
                            get_dated_income_records_raw(list(df["bus_number"].unique()))
                        )
                        avg_mult = (sum(m["multiplier"] for m in multipliers.values()) / len(multipliers)) if multipliers else 1.3
                        total_forecast = sum(f["forecast_income"] for f in income_forecast.values())
                        boosted = total_forecast * avg_mult
                        st.info(
                            f"🎉 {fest_soon[0]['name']} isi window mein aa raha hai — historically income "
                            f"~{avg_mult:.1f}x tak badhta hai. Adjusted estimate: ~₹{boosted:,.0f} "
                            f"(plain trend forecast: ₹{total_forecast:,.0f})"
                        )

            if has_diesel and has_income:
                st.markdown("**💰 Payment vs ⛽ Est. Diesel Cost:**")
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Payment", x=summary["Bus"].tolist(), y=summary["Payment"],
                    marker_color="#14A085",
                    text=summary["Payment"].astype(int), textposition="outside",
                ))
                fig.add_trace(go.Bar(
                    name="Est Diesel Cost", x=summary["Bus"].tolist(), y=summary["Est_Diesel_Cost"],
                    marker_color="#FF5252",
                    text=summary["Est_Diesel_Cost"].astype(int), textposition="outside",
                ))
                max_v = max(summary["Payment"].max(), summary["Est_Diesel_Cost"].max())
                fig.update_layout(
                    barmode="group", yaxis_title="₹",
                    xaxis=dict(type="category"),
                    yaxis=dict(range=[0, max_v * 1.2], gridcolor="rgba(255,255,255,0.08)"),
                    bargap=0.25, bargroupgap=0.05,
                )
                _render_chart(_plotly_dark(fig), key="qo_chart_income_vs_diesel")
                _show_insight(f"""
Bus financial data: {summary[['Bus','Payment','Est_Diesel_Cost','Net']].to_dict('records')}

Analyze profitability and respond in this exact format:
🟢 Strengths
• [most profitable bus — name, payment, net profit]

🟠 Opportunities
• [bus with high diesel cost eating into profit — name it]

🔴 Critical Issues
• [bus with negative or zero net profit — name it]

💡 Recommendations
• [diesel reduction strategy or route optimization]

📈 Overall Status: Excellent / Good / Average / Poor
Max 2 bullets per section. Use rupee amounts.
""")

    with tab7:
        alert_df = df[df["diesel"] > 0][
            ["date_str", "bus_number", "driver_name", "actual_km", "diesel_km", "diesel", "km_per_litre", "mileage_zscore", "alert_status"]
        ].rename(columns={
            "date_str":    "Date",      "bus_number":  "Bus",
            "driver_name": "Driver",    "actual_km":   "Actual KM",
            "diesel_km":   "Diesel KM", "diesel":      "Diesel (L)",
            "km_per_litre":"Mileage (KM/L)", "mileage_zscore": "Z-score", "alert_status": "Status",
        }).sort_values("Date")

        red_flags = alert_df[alert_df["Status"] == "🚨 Red flag"]
        checks    = alert_df[alert_df["Status"] == "⚠️ Check"]

        m1, m2, m3 = st.columns(3)
        m1.metric("🚨 Red flags",        len(red_flags))
        m2.metric("⚠️ Low mileage days", len(checks))
        m3.metric("✅ Normal days",       len(alert_df[alert_df["Status"] == "✅ Normal"]))

        if len(red_flags) > 0:
            st.error(f"{len(red_flags)} din aisa hain jaha diesel liya gaya lekin gaadi chali nahi!")

        with st.expander("📊 Har bus ka seekha hua mileage baseline"):
            if mileage_baseline:
                st.dataframe(pd.DataFrame(baseline_summary_rows(mileage_baseline)), width='stretch', hide_index=True)
            else:
                st.caption("Abhi tak kisi bus ka diesel data nahi mila.")

        # ── Mileage trend + baseline band overlay — line kab band se bahar gayi, visually dikhta hai ──
        buses_with_baseline = [b for b in alert_df["Bus"].unique() if b in mileage_baseline and mileage_baseline[b]["count"] >= MIN_HISTORY_FOR_ML]
        if buses_with_baseline:
            st.markdown("**📉 Mileage Trend vs Learned Baseline**")
            band_fig = go.Figure()
            for i, bus in enumerate(buses_with_baseline):
                bus_data = alert_df[alert_df["Bus"] == bus].sort_values("Date")
                base = mileage_baseline[bus]
                mean, std = base["mean"], base["std"]
                color = bus_color_map.get(str(bus), COLORS[i % len(COLORS)])

                # Shaded band: mean ± 1 std deviation
                band_fig.add_trace(go.Scatter(
                    x=list(bus_data["Date"]) + list(bus_data["Date"])[::-1],
                    y=[mean + std] * len(bus_data) + [mean - std] * len(bus_data),
                    fill="toself", fillcolor="rgba(255,255,255,0.06)",
                    line=dict(color="rgba(0,0,0,0)"), showlegend=False,
                    hoverinfo="skip", name=f"{bus} band",
                ))
                # Actual mileage line
                band_fig.add_trace(go.Scatter(
                    x=bus_data["Date"], y=bus_data["Mileage (KM/L)"],
                    mode="lines+markers", name=bus,
                    line=dict(color=color, width=2),
                    marker=dict(
                        size=7,
                        color=["#FF5252" if s == "🚨 Red flag" else "#FFB347" if s == "⚠️ Check" else color
                               for s in bus_data["Status"]],
                    ),
                    hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>%{y:.2f} km/L<extra></extra>",
                ))
            band_fig.update_layout(
                xaxis_title="Date", yaxis_title="Mileage (KM/L)",
                margin=dict(t=20, b=10, l=10, r=10),
            )
            _render_chart(_plotly_dark(band_fig), key="qo_chart_mileage_band")
            st.caption("Halki shaded band = bus ka normal range (mean ± 1 std dev). Red/orange dots = flagged din.")

        # ── Vehicle Health Score — mileage + income + maintenance ek saath combine ──
        st.markdown("**🏥 Fleet Health Score**")
        mileage_z_by_bus = df.groupby("bus_number")["mileage_zscore"].mean().to_dict()
        income_z_by_bus  = df.groupby("bus_number")["income_zscore"].mean().to_dict()
        maintenance_overdue_by_bus = {
            bus: _maintenance_overdue_days(bus) for bus in df["bus_number"].unique()
        }
        fleet_health = compute_fleet_health(
            list(df["bus_number"].unique()), mileage_z_by_bus, income_z_by_bus, maintenance_overdue_by_bus
        )
        health_cols = st.columns(len(fleet_health)) if fleet_health else []
        for i, (bus, h) in enumerate(fleet_health.items()):
            with health_cols[i]:
                st.metric(bus, f"{h['score']}/100", h["label"])
                for reason in h["reasons"][:2]:
                    st.caption(f"• {reason}")

        # ── Multivariate Anomaly Detection — mileage + income + KM ek saath dekh kar pattern pakadta hai ──
        st.markdown("**🧬 Combined (Multivariate) Anomaly Detection**")
        st.caption("Mileage + Income + KM ek saath dekh kar pattern anomaly pakadta hai (Isolation Forest)")
        mv_input = df[df["actual_km"] > 0][
            ["bus_number", "date_str", "driver_name", "km_per_litre", "income_per_km", "actual_km"]
        ].copy()
        mv_result = detect_multivariate_anomalies(mv_input)
        mv_flags = mv_result[mv_result["is_anomaly"] == True].sort_values("anomaly_score")
        if not mv_flags.empty:
            st.dataframe(
                mv_flags.rename(columns={
                    "bus_number": "Bus", "date_str": "Date", "driver_name": "Driver",
                    "km_per_litre": "Mileage (KM/L)", "income_per_km": "Income/KM",
                    "actual_km": "Actual KM", "anomaly_score": "Anomaly Score",
                })[["Date", "Bus", "Driver", "Mileage (KM/L)", "Income/KM", "Actual KM", "Anomaly Score"]],
                width='stretch', hide_index=True,
            )
        else:
            st.caption("Koi combined anomaly nahi mila (ya kaafi records nahi hain kisi bus ke paas abhi ML ke liye).")

        st.dataframe(alert_df, width='stretch', hide_index=True)
        _show_insight(f"""
Anomaly detection: per-bus ML baseline (mean ± std deviation), z-score <= -1.5 flags Check, <= -2.5 flags Red flag. Naye bus fallback reference: {FALLBACK_MIN_MILEAGE} km/L tak {MIN_HISTORY_FOR_ML} records na ho jaayein.
Red flags (diesel taken, 0 KM): {len(red_flags)}
Low mileage days: {len(checks)}
Alert details: {alert_df[['Bus','Driver','Diesel KM','Diesel (L)','Mileage (KM/L)','Status']].head(5).to_dict('records')}

Analyze fuel alerts and respond in this exact format:
🟢 Strengths
• [days with normal mileage — count and avg]

🟠 Opportunities
• [buses with recurring low mileage — name them]

🔴 Critical Issues
• [red flag buses — diesel taken but 0 KM — name driver and bus]

💡 Recommendations
• [maintenance priority, driver investigation, or fuel audit]

📈 Overall Status: Excellent / Good / Average / Poor
Max 2 bullets per section. Name specific buses and drivers.
""")

    with tab8:
        ipk_conductor = (df.assign(conductor_name=df["conductor_name"].str.strip().str.lower())
            .groupby("conductor_name")
            .agg(Income=("income", "sum"), Actual_KM=("actual_km", "sum"))
            .reset_index()
            .rename(columns={"conductor_name": "Conductor"})
        )
        ipk_conductor = ipk_conductor[
            (ipk_conductor["Actual_KM"] > 0) &
            (ipk_conductor["Conductor"].str.strip() != "") &
            (~ipk_conductor["Conductor"].isin(["none", "nan", ""]))
        ]
        ipk_conductor["Income_per_KM"] = (ipk_conductor["Income"] / ipk_conductor["Actual_KM"]).round(2)
        ipk_conductor = ipk_conductor.sort_values("Income_per_KM", ascending=False)

        if ipk_conductor.empty:
            st.info("Conductor data available nahi hai — vehicle records mein conductor fill karo.")
        else:
            bar_colors = [COLORS[i % len(COLORS)] for i in range(len(ipk_conductor))]
            fig = go.Figure(go.Bar(
                x=ipk_conductor["Conductor"], y=ipk_conductor["Income_per_KM"],
                marker_color=bar_colors,
                text=ipk_conductor["Income_per_KM"], textposition="outside",
                texttemplate="₹%{text}",
            ))
            max_v = ipk_conductor["Income_per_KM"].max()
            fig.update_layout(
                xaxis_title="Conductor", yaxis_title="Income per KM (₹)",
                xaxis=dict(type="category"),
                yaxis=dict(range=[0, max_v * 1.2], gridcolor="rgba(255,255,255,0.08)"),
            )
            _render_chart(_plotly_dark(fig), key="qo_chart_income_per_km")
            _show_insight(f"""
Conductor revenue data: {ipk_conductor[['Conductor','Income_per_KM','Actual_KM']].to_dict('records')}

Analyze conductor revenue efficiency and respond in this exact format:
🟢 Strengths
• [top conductor name, income/km, total KM]

🟠 Opportunities
• [conductor with high KM but low income/km — possible fare leakage]

🔴 Critical Issues
• [conductor with lowest income/km — name them, possible cause]

💡 Recommendations
• [revenue audit, route change, or recognition]

📈 Overall Status: Excellent / Good / Average / Poor
Max 2 bullets per section. Name conductors specifically.
""")
            st.dataframe(ipk_conductor, width='stretch', hide_index=True)

        # ── Conductor income trend — apne hi past se compare, declining conductors upar ──
        conductor_raw = [
            {**r, "conductor": (r.get("conductor_name") or "").strip()}
            for r in get_conductor_income_records_raw(list(df["bus_number"].unique()))
            if (r.get("conductor_name") or "").strip().lower() not in ("", "none", "no", "test")
        ]
        conductor_trends = compute_conductor_income_trends(conductor_raw)
        if conductor_trends:
            st.markdown("**📈 Conductor Income Trend (apne hi past se compare)**")
            trend_rows = conductor_income_trend_rows(conductor_trends)
            declining = [r for r in trend_rows if r["Trend"] == "📉 Declining"]
            if declining:
                names = ", ".join(r["Conductor"].title() for r in declining)
                st.warning(f"⚠️ Income/km girta ja raha hai: {names} — inko check karo.")
            st.dataframe(pd.DataFrame(trend_rows), width='stretch', hide_index=True)

        # ── Festival-day conductor performance — sirf festival window records par ──
        fest_perf = conductor_festival_performance(conductor_raw)
        if fest_perf:
            with st.expander("🎉 Festival Days — Conductor Performance"):
                st.caption("Sirf festival window ke records — bheed ko sabse achhe se kaun cash karta hai")
                st.dataframe(pd.DataFrame(fest_perf), width='stretch', hide_index=True)

        # ── Income anomaly detection (baseline pehle se compute ho chuka hai upar) ──
        day_income = df[df["actual_km"] > 0][
            ["date_str", "bus_number", "driver_name", "actual_km", "income", "income_per_km"]
        ].copy()
        day_income["Alert"] = day_income.apply(
            lambda r: income_alert_status(r["bus_number"], r["actual_km"], r["income_per_km"], income_baseline),
            axis=1,
        )
        income_flags = day_income[day_income["Alert"].isin(["🚨 Red flag", "⚠️ Check"])]

        st.markdown("#### 🔍 Income Anomaly Detection")
        ic1, ic2 = st.columns(2)
        ic1.metric("🚨 Red flags (revenue leakage suspect)", len(day_income[day_income["Alert"] == "🚨 Red flag"]))
        ic2.metric("⚠️ Low-income days",                     len(day_income[day_income["Alert"] == "⚠️ Check"]))

        with st.expander("📊 Har bus ka seekha hua income baseline"):
            if income_baseline:
                st.dataframe(pd.DataFrame(income_baseline_summary_rows(income_baseline)), width='stretch', hide_index=True)
            else:
                st.caption("Abhi tak kaafi income data nahi mila.")

        if not income_flags.empty:
            st.dataframe(
                income_flags.rename(columns={
                    "date_str": "Date", "bus_number": "Bus", "driver_name": "Driver",
                    "actual_km": "Actual KM", "income": "Income", "income_per_km": "Income/KM",
                }),
                width='stretch', hide_index=True,
            )
        else:
            st.caption("Koi income anomaly nahi mila is period me.")

    with tab9:
        total_payment  = summary["Payment"].sum()
        total_est_cost = summary["Est_Diesel_Cost"].sum()
        net_profit     = total_payment - total_est_cost
        total_alerts   = (df["alert_status"] == "🚨 Red flag").sum()

        best_conductor_row = (
            ipk_conductor.iloc[0]
            if 'ipk_conductor' in locals() and not ipk_conductor.empty
            else None
        )

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("💰 Payment",            f"₹{total_payment:,.0f}")
        s2.metric("⛽ Est. Diesel Cost",   f"₹{total_est_cost:,.0f}")
        s3.metric("📈 Net (est.)",         f"₹{net_profit:,.0f}")
        s4.metric("🚨 Alerts this period", int(total_alerts))

        if best_conductor_row is not None:
            st.markdown(f"""
            <div style='background:#14A085;border-radius:12px;padding:16px;margin-top:12px;
                        border:1px solid rgba(255,255,255,0.2);'>
                <span style='color:#d0f5ee;font-size:0.85rem;'>🏆 Best conductor (income/km)</span><br>
                <span style='color:white;font-size:1.2rem;font-weight:700;'>{best_conductor_row["Conductor"].title()}</span>
                <span style='color:#FFD700;font-size:1rem;'> — ₹{best_conductor_row["Income_per_KM"]}/km</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Bus wise net profit (Payment ke hisaab se):**")

        # ── Bus profitability segmentation — High Profit / Moderate / Loss-making ──
        bus_perf = summary.copy()
        bus_perf["Income_per_KM"]       = (bus_perf["Payment"] / bus_perf["Actual_KM"].replace(0, float("nan"))).round(2)
        bus_perf["Diesel_Cost_per_KM"]  = (bus_perf["Est_Diesel_Cost"] / bus_perf["Actual_KM"].replace(0, float("nan"))).round(2)
        bus_perf["Net_Profit"]          = bus_perf["Net"]
        bus_perf = segment_bus_profitability(
            bus_perf[["Bus", "Income_per_KM", "Diesel_Cost_per_KM", "Net_Profit"]].fillna(0)
        )
        display_summary = summary[["Bus", "Payment", "Diesel", "Diesel_Rate", "Est_Diesel_Cost", "Net"]].copy()
        display_summary = display_summary.merge(bus_perf[["Bus", "Segment"]], on="Bus", how="left")
        display_summary.columns = ["Bus", "Payment", "Diesel (L)", "Rate (₹/L)", "Est. Diesel Cost", "Net", "Segment"]
        st.dataframe(display_summary, width='stretch', hide_index=True)

        # ── Fleet-benchmark features — ye wahi cheez hai jo LLM ko "insight"
        #    dene layak banati hai, sirf raw totals dekh ke nahi ──
        insight_df = summary.copy()
        insight_df["Diesel_Cost_Pct_of_Payment"] = (insight_df["Est_Diesel_Cost"] / insight_df["Payment"].replace(0, float("nan")) * 100).round(1)
        insight_df["Net_Margin_Pct"]              = (insight_df["Net"] / insight_df["Payment"].replace(0, float("nan")) * 100).round(1)
        insight_df["Payment_per_KM"]               = (insight_df["Payment"] / insight_df["Actual_KM"].replace(0, float("nan"))).round(2)

        fleet_avg = {
            "Diesel_Cost_Pct_of_Payment": round(insight_df["Diesel_Cost_Pct_of_Payment"].mean(skipna=True), 1),
            "Net_Margin_Pct":              round(insight_df["Net_Margin_Pct"].mean(skipna=True), 1),
            "Payment_per_KM":              round(insight_df["Payment_per_KM"].mean(skipna=True), 2),
        }
        insight_df["Diesel_Pct_vs_Fleet_Avg"] = (insight_df["Diesel_Cost_Pct_of_Payment"] - fleet_avg["Diesel_Cost_Pct_of_Payment"]).round(1)
        insight_df["Margin_vs_Fleet_Avg"]     = (insight_df["Net_Margin_Pct"] - fleet_avg["Net_Margin_Pct"]).round(1)

        # ── ML signals already computed upar (tab7/tab8) ko yahin reuse karo —
        #    inhi se "WHY" nikalta hai, sirf totals se nahi ──
        mileage_z_summary = df.groupby("bus_number")["mileage_zscore"].mean().round(2).to_dict()
        income_z_summary  = df.groupby("bus_number")["income_zscore"].mean().round(2).to_dict()
        alerts_by_bus      = df[df["alert_status"] == "🚨 Red flag"].groupby("bus_number").size().to_dict()
        health_by_bus       = {bus: h["score"] for bus, h in fleet_health.items()} if 'fleet_health' in locals() else {}

        insight_records = []
        for _, row in insight_df.iterrows():
            bus = row["Bus"]
            insight_records.append({
                "Bus": bus,
                "Payment": row["Payment"], "Net": row["Net"],
                "Diesel_Cost_Pct_of_Payment": row["Diesel_Cost_Pct_of_Payment"],
                "vs_fleet_avg_diesel_pct": row["Diesel_Pct_vs_Fleet_Avg"],
                "Net_Margin_Pct": row["Net_Margin_Pct"],
                "vs_fleet_avg_margin": row["Margin_vs_Fleet_Avg"],
                "Payment_per_KM": row["Payment_per_KM"],
                "avg_mileage_zscore": mileage_z_summary.get(bus),
                "avg_income_zscore": income_z_summary.get(bus),
                "red_flag_alerts": int(alerts_by_bus.get(bus, 0)),
                "health_score": health_by_bus.get(bus),
            })

        _show_insight(f"""
Period: {period_label}
Fleet averages this period: Diesel cost is {fleet_avg['Diesel_Cost_Pct_of_Payment']}%% of payment on average, Net margin is {fleet_avg['Net_Margin_Pct']}%% on average, Payment per KM averages Rs{fleet_avg['Payment_per_KM']}.

Per-bus data with deviation from fleet average (use these exact numbers only):
{insight_records}
Total Payment: Rs{total_payment:,.0f}
Total Diesel Cost: Rs{total_est_cost:,.0f}
Net Profit: Rs{net_profit:,.0f}
Mileage Alerts: {int(total_alerts)}

FIRST check each bus for data issues and tag them inline — include ALL buses in analysis:
- Diesel = 0 but Payment > 0 -> tag as [diesel entry missing]
- Diesel = 0 but KM > 0 -> tag as [data error: bus cannot run without fuel]
- Payment = 0 but Diesel > 0 -> tag as [revenue missing]
- Net > Payment -> tag as [calculation error]

Respond in this exact format:
⚠️ Data Quality Issues
• [bus name + exact issue]

🟢 Strengths (all buses, tag flagged ones)
• [bus whose ratio beats fleet average by the widest margin — name the ratio and the gap, not just the total]

🟠 Opportunities (all buses, tag flagged ones)
• [bus with a hidden margin problem — decent payment but diesel-cost-pct or margin worse than fleet average — name the gap]

🔴 Critical Issues (all buses, tag flagged ones)
• [bus where a low mileage/income z-score or red-flag alert count explains WHY the net number looks bad — connect the signals]

💡 Recommendations
• [one specific action tied to the exact ratio/signal named above, not a generic tip]

📈 Overall Status: Excellent / Good / Average / Poor
Every bullet must reference a ratio, a deviation from fleet average, or a connection between two signals. Restating a raw total alone is not acceptable.
""")

    if st.button("🔄 Refresh Overview", key="refresh_overview"):
        st.session_state.pop(cache_key, None)
        st.rerun()
