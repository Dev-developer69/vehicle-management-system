import streamlit as st
import pandas as pd
from datetime import date

from src.database.auth import get_accessible_vehicles
from src.database.db import (
    get_vehicle_records, get_fuel_fills, get_vehicle_expenses, get_driver_salary,
    get_maintenance_records, get_vehicle_payment_config, get_driver_rate,
    get_vehicle_compliance, save_vehicle_compliance,
)
from src.ui.excel_format import _get_date_range, fuel_label, _render_html_table


def _page_style():
    """Bus Report page ka background color (deep maroon/amber theme) +
    mobile-responsive font/padding fixes + Streamlit ka default
    header/toolbar hide (login_page jaisa hi pattern)."""
    st.markdown("""
        <style>
            [data-testid="stAppViewContainer"] {
                background: #2B1518 !important;
            }
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            #MainMenu {
                display: none !important;
                height: 0 !important;
                visibility: hidden !important;
            }
            .block-container {
                padding-top: 1.5rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
                max-width: 100% !important;
            }

            /* ── Mobile fixes: chhoti screens pe text readable rahe ── */
            @media (max-width: 640px) {
                .block-container {
                    padding-left: 0.6rem !important;
                    padding-right: 0.6rem !important;
                }
                [data-testid="column"] {
                    min-width: 100% !important;
                    flex: 1 1 100% !important;
                }
                h3, h4 {
                    font-size: 1.05rem !important;
                }
            }
        </style>
    """, unsafe_allow_html=True)


def _compute_final_payment(bus_number: str, total_income: float, total_actual_km: float):
    """Vehicle Records ke 'Payment Summary' jaisa hi calculation — Standard
    ya IPKM Slab method, saved config ke hisaab se. Returns (raw_payment,
    final_payment, tax_pct)."""
    cfg = get_vehicle_payment_config(bus_number)
    PERIOD_TAX = 11700
    if cfg["method"] == "standard":
        raw = total_income - (total_actual_km * cfg["rate"]) - PERIOD_TAX
        tax_pct = 0.01
    else:
        ipkm = (total_income - PERIOD_TAX) / total_actual_km if total_actual_km > 0 else 0
        if ipkm < cfg["ipkm_threshold"]:
            raw = (ipkm - cfg["ipkm_deduction"]) * total_actual_km
        else:
            raw = (cfg["ipkm_threshold"] - cfg["ipkm_deduction"]) * total_actual_km
        tax_pct = 0.02
    final = raw - (raw * tax_pct) - cfg["final_deduction"]
    return raw, final, tax_pct


def _compute_period_metrics(vr_sub, fills_sub, exp_sub, sal_sub, bus_number):
    """Ek date-range (poora period ya half) ke liye saare summary metrics ek
    saath nikalta hai — full period aur 1-15/16-31 split, dono ke liye
    reuse hota hai."""
    present_days    = len(vr_sub[vr_sub["Status"] == "Present"]) if not vr_sub.empty else 0
    leave_days      = len(vr_sub[vr_sub["Status"] == "On Leave"]) if not vr_sub.empty else 0
    total_actual_km = pd.to_numeric(vr_sub["Actual KM"], errors="coerce").fillna(0).sum() if not vr_sub.empty else 0.0
    total_sched_km  = pd.to_numeric(vr_sub["Scheduled KM"], errors="coerce").fillna(0).sum() if not vr_sub.empty else 0.0
    efficiency      = round(total_actual_km / total_sched_km * 100, 1) if total_sched_km > 0 else 0.0
    total_income    = pd.to_numeric(vr_sub["Income"], errors="coerce").fillna(0).sum() if not vr_sub.empty else 0.0

    total_diesel      = float(fills_sub["Quantity"].sum()) if not fills_sub.empty else 0.0
    total_diesel_cost = float(fills_sub["Amount"].sum())   if not fills_sub.empty else 0.0
    diesel_days       = int(fills_sub["Date"].nunique())   if not fills_sub.empty else 0
    total_diesel_km   = pd.to_numeric(vr_sub["Diesel KM"], errors="coerce").fillna(0).sum() if not vr_sub.empty else 0.0

    diesel_km_rows  = vr_sub[pd.to_numeric(vr_sub["Diesel KM"], errors="coerce").fillna(0) > 0] if not vr_sub.empty else vr_sub
    diesel_km_dates = set(pd.to_datetime(diesel_km_rows["Date"]).dt.strftime("%Y-%m-%d")) if not diesel_km_rows.empty else set()
    diesel_for_km_calc = (
        float(fills_sub[pd.to_datetime(fills_sub["Date"]).dt.strftime("%Y-%m-%d").isin(diesel_km_dates)]["Quantity"].sum())
        if not fills_sub.empty and diesel_km_dates else 0.0
    )
    avg_via_diesel_km = round(total_diesel_km / diesel_for_km_calc, 2) if diesel_for_km_calc > 0 else 0.0
    avg_via_actual_km = round(total_actual_km / total_diesel, 2) if total_diesel > 0 else 0.0

    raw_payment, final_payment, tax_pct = _compute_final_payment(bus_number, total_income, total_actual_km)

    total_expenses = pd.to_numeric(exp_sub["Amount"], errors="coerce").fillna(0).sum() if not exp_sub.empty else 0.0
    total_salary   = pd.to_numeric(sal_sub["Salary"], errors="coerce").fillna(0).sum() if not sal_sub.empty else 0.0

    expected_salary = 0.0
    if not vr_sub.empty:
        duty_df = vr_sub[vr_sub["Status"] != "On Leave"].copy()
        duty_df = duty_df[
            duty_df["Driver Name"].notna()
            & (duty_df["Driver Name"].astype(str).str.strip().str.lower() != "none")
        ]
        if not duty_df.empty:
            duties_by_driver = duty_df.groupby(duty_df["Driver Name"].astype(str).str.strip())["Date"].nunique().to_dict()
            for driver_name, duties in duties_by_driver.items():
                rate = get_driver_rate(bus_number, driver_name)
                expected_salary += duties * rate

    return {
        "present_days": present_days, "leave_days": leave_days,
        "actual_km": total_actual_km, "efficiency": efficiency,
        "diesel": total_diesel, "diesel_cost": total_diesel_cost, "diesel_days": diesel_days,
        "avg_diesel_km": avg_via_diesel_km, "avg_actual_km": avg_via_actual_km,
        "raw_payment": raw_payment, "final_payment": final_payment, "tax_pct": tax_pct,
        "expenses": total_expenses, "salary_paid": total_salary, "expected_salary": expected_salary,
    }


def _filter_by_range(df, start, end, date_col="Date"):
    """Ek dataframe ko given date-range ke andar filter karta hai — 01-31
    period select hone par usko 1-15/16-31 halves me todne ke liye."""
    if df.empty:
        return df
    d = pd.to_datetime(df[date_col])
    return df[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))]


def _p_suffix(p1_val, p2_val, fmt):
    """Dono halves (1-15 aur 16-31) ki values sirf number/unit ke saath
    dikhata hai — bina 'periodname:' label ke, jaise '12 days · 0 days'."""
    return f"{fmt(p1_val)}  ·  {fmt(p2_val)}"


def _validity_status(label: str, val_date):
    """Insurance/Fitness/Pollution/Road Tax jaisi validity dates ke liye
    ✅/⚠️/❌ status dikhata hai — Driver Report ke license-status jaisa hi."""
    if not val_date:
        st.caption(f"{label}: set nahi hai")
        return
    d = pd.to_datetime(val_date).date()
    days_left = (d - date.today()).days
    if days_left < 0:
        st.error(f"❌ {label} EXPIRED {abs(days_left)} din pehle ({d})")
    elif days_left <= 30:
        st.warning(f"⚠️ {label} {days_left} din me expire ho rahi hai ({d})")
    else:
        st.success(f"✅ {label} valid ({d} tak)")


def _metric_card(label: str, value: str, sublabel: str = ""):
    """App-wide gradient-card style (maroon/amber theme) — plain st.metric ke
    bajaye consistent look ke liye. Font-sizes clamp() se scale hote hain
    taaki mobile pe bhi text chhota/crushed na lage aur readable rahe."""
    sub_html = (
        f"<div style='color:#f5d9cf;font-size:clamp(0.68rem,2.6vw,0.78rem);"
        f"margin-top:3px;'>{sublabel}</div>"
        if sublabel else ""
    )
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#8B3A3A,#2B1518);border-radius:12px;
                padding:14px;text-align:center;border:1px solid rgba(255,255,255,0.18);
                min-height:88px;'>
        <div style='color:#f5d9cf;font-size:clamp(0.72rem,2.8vw,0.85rem);'>{label}</div>
        <div style='color:white;font-size:clamp(1.05rem,4.2vw,1.35rem);font-weight:700;margin-top:4px;'>{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def bus_report_view():
    _page_style()

    top_l, top_r = st.columns([5, 1])
    with top_l:
        st.markdown("### 🚌 Bus Report")
    with top_r:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🏠 Home", key="br_home_btn", width='stretch'):
            st.session_state['login_state'] = None
            st.rerun()

    accessible = get_accessible_vehicles()
    if not accessible:
        st.info("Koi accessible vehicle nahi mila.")
        return

    bus_number = st.selectbox("Bus chuno", options=accessible, key="br_bus")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        br_month = st.selectbox(
            "Month", options=list(range(1, 13)), index=date.today().month - 1,
            format_func=lambda x: date(2000, x, 1).strftime("%B"), key="br_month",
        )
    with col2:
        br_period = st.radio("Period", ["1-15", "16-31", "01-31"], index=2, horizontal=True, key="br_period")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        load = st.button("🔄 Load Report", key="br_load", type='primary', width='stretch')

    year = date.today().year
    start, end = _get_date_range(year, br_month, br_period)
    from_date, to_date = str(start.date()), str(end.date())

    st.markdown("---")

    # ── Vehicle Info & Compliance (editable) ──
    st.markdown("#### 📋 Vehicle Info & Compliance")
    comp = get_vehicle_compliance(bus_number)

    def _default_date(key):
        return pd.to_datetime(comp[key]).date() if comp.get(key) else date.today()

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        owner_name = st.text_input("Owner Name", value=comp.get("owner_name") or "", key="br_owner")
        route_name = st.text_input("Route Name", value=comp.get("route_name") or "", key="br_route")
    with cc2:
        capacity = st.number_input("Capacity", min_value=0, value=int(comp.get("capacity") or 0), key="br_capacity")
        registration_date = st.date_input("Registration Date", value=_default_date("registration_date"), key="br_reg_date")
    with cc3:
        insurance_validity = st.date_input("Insurance Validity", value=_default_date("insurance_validity"), key="br_insurance")
        fitness_validity   = st.date_input("Fitness Validity",   value=_default_date("fitness_validity"),   key="br_fitness")

    cc4, cc5 = st.columns(2)
    with cc4:
        pollution_validity = st.date_input("Pollution (PUC) Validity", value=_default_date("pollution_validity"), key="br_pollution")
    with cc5:
        road_tax_validity   = st.date_input("Road Tax Validity",        value=_default_date("road_tax_validity"),   key="br_roadtax")

    if st.button("💾 Save Vehicle Info", key="br_save_compliance"):
        save_vehicle_compliance(
            bus_number,
            owner_name=owner_name, route_name=route_name, capacity=capacity,
            registration_date=str(registration_date),
            insurance_validity=str(insurance_validity),
            fitness_validity=str(fitness_validity),
            pollution_validity=str(pollution_validity),
            road_tax_validity=str(road_tax_validity),
        )
        st.success("✅ Vehicle info saved!")
        st.rerun()

    st.markdown("**Validity Status:**")
    vc1, vc2, vc3, vc4 = st.columns(4)
    with vc1:
        _validity_status("Insurance", comp.get("insurance_validity"))
    with vc2:
        _validity_status("Fitness", comp.get("fitness_validity"))
    with vc3:
        _validity_status("Pollution (PUC)", comp.get("pollution_validity"))
    with vc4:
        _validity_status("Road Tax", comp.get("road_tax_validity"))

    st.markdown("---")

    # ── Period ka data fetch (cached) ──
    report_key = f"br_report_{bus_number}_{from_date}_{to_date}"
    if load or report_key not in st.session_state:
        vr = get_vehicle_records(bus_number)
        if not vr.empty:
            vr["Date"] = pd.to_datetime(vr["Date"])
            vr = vr[(vr["Date"] >= pd.Timestamp(from_date)) & (vr["Date"] <= pd.Timestamp(to_date))]

        fills = get_fuel_fills(bus_number, from_date, to_date)

        exp = get_vehicle_expenses(bus_number)
        if not exp.empty:
            exp["Date"] = pd.to_datetime(exp["Date"])
            exp = exp[(exp["Date"] >= pd.Timestamp(from_date)) & (exp["Date"] <= pd.Timestamp(to_date))]

        sal = get_driver_salary(bus_number=bus_number)
        if not sal.empty:
            sal["Date"] = pd.to_datetime(sal["Date"])
            sal = sal[(sal["Date"] >= pd.Timestamp(from_date)) & (sal["Date"] <= pd.Timestamp(to_date))]

        maint = get_maintenance_records(bus_number)

        st.session_state[report_key] = {"vr": vr, "fills": fills, "exp": exp, "sal": sal, "maint": maint}

    data = st.session_state[report_key]
    vr, fills, exp, sal, maint = data["vr"], data["fills"], data["exp"], data["sal"], data["maint"]

    if vr.empty:
        st.info(f"📭 {bus_number} ke liye {date(2000, br_month, 1).strftime('%B')} ({br_period}) me koi record nahi mila.")
        return

    # ── Poore period (full/half, jo bhi selected hai) ke metrics ──
    full = _compute_period_metrics(vr, fills, exp, sal, bus_number)

    # ── Agar poora month (01-31) selected hai, to 1-15 aur 16-31 ke
    # metrics alag se nikalo — har card ke sublabel me dono halves ka
    # breakdown suffix ke roop me dikhane ke liye ──
    show_split = (br_period == "01-31")
    p1_metrics = p2_metrics = None
    if show_split:
        p1_start, p1_end = _get_date_range(year, br_month, "1-15")
        p2_start, p2_end = _get_date_range(year, br_month, "16-31")

        vr_p1  = _filter_by_range(vr,  p1_start, p1_end)
        vr_p2  = _filter_by_range(vr,  p2_start, p2_end)
        fills_p1 = _filter_by_range(fills, p1_start, p1_end)
        fills_p2 = _filter_by_range(fills, p2_start, p2_end)
        exp_p1 = _filter_by_range(exp, p1_start, p1_end)
        exp_p2 = _filter_by_range(exp, p2_start, p2_end)
        sal_p1 = _filter_by_range(sal, p1_start, p1_end)
        sal_p2 = _filter_by_range(sal, p2_start, p2_end)

        p1_metrics = _compute_period_metrics(vr_p1, fills_p1, exp_p1, sal_p1, bus_number)
        p2_metrics = _compute_period_metrics(vr_p2, fills_p2, exp_p2, sal_p2, bus_number)

    def _sub(base_sublabel, key, fmt):
        """Existing sublabel (jaise '17 din') ke saath 1-15/16-31 breakdown
        jodta hai — sirf jab 01-31 selected ho."""
        if not show_split:
            return base_sublabel
        split_txt = _p_suffix(p1_metrics[key], p2_metrics[key], fmt)
        return f"{base_sublabel}  ·  {split_txt}" if base_sublabel else split_txt

    fmt_int   = lambda v: f"{v:.0f} days"
    fmt_km    = lambda v: f"{v:,.0f} km"
    fmt_pct   = lambda v: f"{v}%"
    fmt_l     = lambda v: f"{v:.2f} L"
    fmt_rs    = lambda v: f"₹{v:,.0f}"
    fmt_kml   = lambda v: f"{v:.2f} km/L"

    # ── Duty summary ──
    st.markdown(f"#### 📊 {bus_number} — {date(2000, br_month, 1).strftime('%B')} ({br_period}) Summary")
    s1, s2, s3, s4 = st.columns(4)
    with s1: _metric_card("📅 Present Days", str(full["present_days"]), sublabel=_sub("", "present_days", fmt_int))
    with s2: _metric_card("🏖️ On Leave", str(full["leave_days"]), sublabel=_sub("", "leave_days", fmt_int))
    with s3: _metric_card("🛣️ Actual KM", f"{full['actual_km']:,.0f}", sublabel=_sub("", "actual_km", fmt_km))
    with s4: _metric_card("🎯 Efficiency", f"{full['efficiency']}%", sublabel=_sub("", "efficiency", fmt_pct))

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Diesel/CNG ──
    fuel = fuel_label(bus_number)
    st.markdown(f"#### ⛽ {fuel}")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        _metric_card(f"Total {fuel}", f"{full['diesel']:.2f} L",
                     sublabel=_sub(f"{full['diesel_days']} din", "diesel", fmt_l))
    with d2:
        _metric_card("Total Cost", f"₹{full['diesel_cost']:,.0f}", sublabel=_sub("", "diesel_cost", fmt_rs))
    with d3:
        _metric_card("Avg (Diesel KM basis)", f"{full['avg_diesel_km']:.2f} km/L",
                     sublabel=_sub("", "avg_diesel_km", fmt_kml))
    with d4:
        _metric_card("Avg (Actual KM basis)", f"{full['avg_actual_km']:.2f} km/L",
                     sublabel=_sub("", "avg_actual_km", fmt_kml))

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Payment ──
    st.markdown("#### 💰 Payment")
    p1, p2 = st.columns(2)
    with p1:
        _metric_card("Payment", f"₹{full['raw_payment']:,.0f}",
                     sublabel=_sub("tax/deduction se pehle", "raw_payment", fmt_rs))
    with p2:
        _metric_card("Final Payment", f"₹{full['final_payment']:,.0f}",
                     sublabel=_sub(f"{int(full['tax_pct']*100)}% tax + fixed deduction minus", "final_payment", fmt_rs))

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Expenses & Driver Salary ──
    salary_savings = full["expected_salary"] - full["salary_paid"]

    st.markdown("#### 🧾 Expenses & Driver Salary")
    e1, e2, e3 = st.columns(3)
    with e1:
        _metric_card("Vehicle Expenses", f"₹{full['expenses']:,.0f}", sublabel=_sub("", "expenses", fmt_rs))
    with e2:
        _metric_card("Driver Salary Paid", f"₹{full['salary_paid']:,.0f}", sublabel=_sub("", "salary_paid", fmt_rs))
    with e3:
        _metric_card("Expected Driver Salary", f"₹{full['expected_salary']:,.0f}",
                     sublabel=_sub("duties × per-duty rate se", "expected_salary", fmt_rs))

    st.markdown(f"""
    <div style='background:{"#3D5A2E" if salary_savings >= 0 else "#4a1010"};border-radius:10px;
                padding:12px 20px;margin-top:10px;display:flex;flex-wrap:wrap;
                justify-content:space-between;align-items:center;gap:6px;'>
        <span style='color:#eee;font-size:clamp(0.78rem,2.8vw,0.9rem);'>💰 Salary Savings/Bachat (Expected − Paid)</span>
        <span style='color:{"#9BE38A" if salary_savings >= 0 else "#FF5252"};font-size:clamp(1rem,3.6vw,1.2rem);font-weight:700;'>₹{salary_savings:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Final Bachat ──
    final_bachat = full["final_payment"] - full["diesel_cost"] - full["expenses"] - full["expected_salary"]
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#8B3A3A,#C9A227);border-radius:12px;
                padding:20px;text-align:center;margin-top:16px;'>
        <span style='color:#fff;font-size:clamp(0.8rem,2.8vw,0.9rem);'>Final Bachat (Final Payment − Diesel − Expenses − Expected Driver Salary)</span><br>
        <span style='color:#FFF3D0;font-size:clamp(1.4rem,5.5vw,1.8rem);font-weight:800;'>₹{final_bachat:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Maintenance ──
    st.markdown("#### 🔧 Maintenance")
    if not maint.empty:
        overdue_shown = False
        due_check = maint[maint["Next Due Date"].notna()].copy()
        if not due_check.empty:
            due_check["Next Due Date"] = pd.to_datetime(due_check["Next Due Date"])
            overdue = due_check[due_check["Next Due Date"] < pd.Timestamp(date.today())]
            for _, r in overdue.iterrows():
                st.error(f"⚠️ {r['Service Type']} overdue since {r['Next Due Date'].date()}")
                overdue_shown = True
        if not overdue_shown:
            st.caption("Koi overdue maintenance nahi hai.")
        _render_html_table(maint.drop(columns=["id"], errors="ignore").head(10))
    else:
        st.info("Koi maintenance record nahi mila.")

    # ── Driver Salary detail (is period ke liye) ──
    if not sal.empty:
        st.markdown("#### 👤 Driver Salary Records (is period)")
        show_sal = sal.drop(columns=["id", "Updated By"], errors="ignore").copy()
        show_sal["Date"] = show_sal["Date"].dt.strftime("%Y-%m-%d")
        _render_html_table(show_sal)
