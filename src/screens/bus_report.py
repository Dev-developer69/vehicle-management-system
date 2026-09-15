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
    """Bus Report page ka background color + Streamlit ka default header/toolbar
    hide (login_page jaisa hi pattern)."""
    st.markdown("""
        <style>
            [data-testid="stAppViewContainer"] {
                background: #0D1B1B !important;
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
    """App-wide gradient-card style (Quick Overview ke Summary Cards jaisa
    hi) — plain st.metric ke bajaye consistent look ke liye."""
    sub_html = f"<div style='color:#d0f5ee;font-size:0.7rem;margin-top:3px;'>{sublabel}</div>" if sublabel else ""
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#14A085,#0d2626);border-radius:12px;
                padding:14px;text-align:center;border:1px solid rgba(255,255,255,0.15);
                min-height:88px;'>
        <div style='color:#d0f5ee;font-size:0.78rem;'>{label}</div>
        <div style='color:white;font-size:1.25rem;font-weight:700;margin-top:4px;'>{value}</div>
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

    # ── Duty summary ──
    present_days    = len(vr[vr["Status"] == "Present"]) if not vr.empty else 0
    leave_days      = len(vr[vr["Status"] == "On Leave"]) if not vr.empty else 0
    total_actual_km = pd.to_numeric(vr["Actual KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0
    total_sched_km  = pd.to_numeric(vr["Scheduled KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0
    efficiency      = round(total_actual_km / total_sched_km * 100, 1) if total_sched_km > 0 else 0.0
    total_income    = pd.to_numeric(vr["Income"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0

    st.markdown(f"#### 📊 {bus_number} — {date(2000, br_month, 1).strftime('%B')} ({br_period}) Summary")
    s1, s2, s3, s4 = st.columns(4)
    with s1: _metric_card("📅 Present Days", str(present_days))
    with s2: _metric_card("🏖️ On Leave", str(leave_days))
    with s3: _metric_card("🛣️ Actual KM", f"{total_actual_km:,.0f}")
    with s4: _metric_card("🎯 Efficiency", f"{efficiency}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Diesel/CNG — ab "kitne din ka" suffix ke saath, aur Mileage ki jagah
    # DO alag averages (Diesel KM basis aur Actual KM basis, dono) ──
    fuel              = fuel_label(bus_number)
    total_diesel      = float(fills["Quantity"].sum()) if not fills.empty else 0.0
    total_diesel_cost = float(fills["Amount"].sum())   if not fills.empty else 0.0
    diesel_days       = int(fills["Date"].nunique())   if not fills.empty else 0
    total_diesel_km   = pd.to_numeric(vr["Diesel KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0

    # ✅ "Diesel KM basis" avg — sirf un dates ka diesel use karo jin dates
    # ke liye Diesel KM actually record hua hai, poore period ka total diesel nahi.
    diesel_km_rows  = vr[pd.to_numeric(vr["Diesel KM"], errors="coerce").fillna(0) > 0] if not vr.empty else vr
    diesel_km_dates = set(diesel_km_rows["Date"].dt.strftime("%Y-%m-%d")) if not diesel_km_rows.empty else set()
    diesel_for_km_calc = (
        float(fills[fills["Date"].isin(diesel_km_dates)]["Quantity"].sum())
        if not fills.empty and diesel_km_dates else 0.0
    )

    avg_via_diesel_km = round(total_diesel_km / diesel_for_km_calc, 2) if diesel_for_km_calc > 0 else 0.0
    avg_via_actual_km = round(total_actual_km / total_diesel, 2) if total_diesel > 0 else 0.0

    st.markdown(f"#### ⛽ {fuel}")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        _metric_card(f"Total {fuel}", f"{total_diesel:.2f} L", sublabel=f"{diesel_days} din")
    with d2:
        _metric_card("Total Cost", f"₹{total_diesel_cost:,.0f}")
    with d3:
        _metric_card("Avg (Diesel KM basis)", f"{avg_via_diesel_km:.2f} km/L")
    with d4:
        _metric_card("Avg (Actual KM basis)", f"{avg_via_actual_km:.2f} km/L")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Payment — ab "Total Income" headline nahi, seedha Payment dikhta hai ──
    raw_payment, final_payment, tax_pct = _compute_final_payment(bus_number, total_income, total_actual_km)
    st.markdown("#### 💰 Payment")
    p1, p2 = st.columns(2)
    with p1:
        _metric_card("Payment", f"₹{raw_payment:,.0f}", sublabel="tax/deduction se pehle")
    with p2:
        _metric_card("Final Payment", f"₹{final_payment:,.0f}", sublabel=f"{int(tax_pct*100)}% tax + fixed deduction minus")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Expenses & Driver Salary — Paid ke saath EXPECTED salary bhi (duties
    # × per-duty rate se), taaki "kitna bachaya" pata chale ──
    total_expenses = pd.to_numeric(exp["Amount"], errors="coerce").fillna(0).sum() if not exp.empty else 0.0
    total_salary   = pd.to_numeric(sal["Salary"], errors="coerce").fillna(0).sum() if not sal.empty else 0.0

    expected_salary = 0.0
    if not vr.empty:
        duty_df = vr[vr["Status"] != "On Leave"].copy()
        duty_df = duty_df[
            duty_df["Driver Name"].notna()
            & (duty_df["Driver Name"].astype(str).str.strip().str.lower() != "none")
        ]
        if not duty_df.empty:
            duties_by_driver = duty_df.groupby(duty_df["Driver Name"].astype(str).str.strip())["Date"].nunique().to_dict()
            for driver_name, duties in duties_by_driver.items():
                rate = get_driver_rate(bus_number, driver_name)
                expected_salary += duties * rate

    salary_savings = expected_salary - total_salary

    st.markdown("#### 🧾 Expenses & Driver Salary")
    e1, e2, e3 = st.columns(3)
    with e1:
        _metric_card("Vehicle Expenses", f"₹{total_expenses:,.0f}")
    with e2:
        _metric_card("Driver Salary Paid", f"₹{total_salary:,.0f}")
    with e3:
        _metric_card("Expected Driver Salary", f"₹{expected_salary:,.0f}", sublabel="duties × per-duty rate se")

    st.markdown(f"""
    <div style='background:{"#1B5E20" if salary_savings >= 0 else "#4a1010"};border-radius:10px;
                padding:12px 20px;margin-top:10px;display:flex;justify-content:space-between;align-items:center;'>
        <span style='color:#eee;font-size:0.9rem;'>💰 Salary Savings/Bachat (Expected − Paid)</span>
        <span style='color:{"#69F0AE" if salary_savings >= 0 else "#FF5252"};font-size:1.2rem;font-weight:700;'>₹{salary_savings:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Final Bachat — Final Payment me se diesel cost, expenses, aur
    # EXPECTED driver salary (accrual basis, sirf paid nahi) minus karke ek
    # poora "sab kuch mila ke" bottom-line ──
    final_bachat = final_payment - total_diesel_cost - total_expenses - expected_salary
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#14A085,#7B8CFF);border-radius:12px;
                padding:20px;text-align:center;margin-top:16px;'>
        <span style='color:#fff;font-size:0.9rem;'>Final Bachat (Final Payment − Diesel − Expenses − Expected Driver Salary)</span><br>
        <span style='color:#FFD700;font-size:1.8rem;font-weight:800;'>₹{final_bachat:,.0f}</span>
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
