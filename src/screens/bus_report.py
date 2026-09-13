import streamlit as st
import pandas as pd
from datetime import date

from src.database.auth import get_accessible_vehicles
from src.database.db import (
    get_vehicle_records, get_fuel_fills, get_vehicle_expenses, get_driver_salary,
    get_maintenance_records, get_vehicle_payment_config,
    get_vehicle_compliance, save_vehicle_compliance,
)
from src.ui.excel_format import _get_date_range, fuel_label, _render_html_table


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


def bus_report_view():
    st.markdown("### 🚌 Bus Report")

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

    # ── Duty summary ──
    present_days    = len(vr[vr["Status"] == "Present"]) if not vr.empty else 0
    leave_days      = len(vr[vr["Status"] == "On Leave"]) if not vr.empty else 0
    total_actual_km = pd.to_numeric(vr["Actual KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0
    total_sched_km  = pd.to_numeric(vr["Scheduled KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0
    efficiency      = round(total_actual_km / total_sched_km * 100, 1) if total_sched_km > 0 else 0.0
    total_income    = pd.to_numeric(vr["Income"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0

    st.markdown(f"#### 📊 {bus_number} — {date(2000, br_month, 1).strftime('%B')} ({br_period}) Summary")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("📅 Present Days", present_days)
    s2.metric("🏖️ On Leave", leave_days)
    s3.metric("🛣️ Actual KM", f"{total_actual_km:,.0f}")
    s4.metric("🎯 Efficiency", f"{efficiency}%")

    # ── Diesel/CNG ──
    fuel              = fuel_label(bus_number)
    total_diesel      = float(fills["Quantity"].sum()) if not fills.empty else 0.0
    total_diesel_cost = float(fills["Amount"].sum())   if not fills.empty else 0.0
    total_diesel_km   = pd.to_numeric(vr["Diesel KM"], errors="coerce").fillna(0).sum() if not vr.empty else 0.0
    mileage           = round(total_diesel_km / total_diesel, 2) if total_diesel > 0 else 0.0

    st.markdown(f"#### ⛽ {fuel}")
    d1, d2, d3 = st.columns(3)
    d1.metric(f"Total {fuel}", f"{total_diesel:.2f} L")
    d2.metric("Total Cost", f"₹{total_diesel_cost:,.0f}")
    d3.metric("Mileage", f"{mileage:.2f} km/L")

    # ── Payment ──
    raw_payment, final_payment, tax_pct = _compute_final_payment(bus_number, total_income, total_actual_km)
    st.markdown("#### 💰 Payment")
    p1, p2, p3 = st.columns(3)
    p1.metric("Total Income", f"₹{total_income:,.0f}")
    p2.metric("Raw Payment", f"₹{raw_payment:,.0f}")
    p3.metric("Final Payment", f"₹{final_payment:,.0f}", help=f"{int(tax_pct*100)}% tax + fixed deduction pehle hi minus")

    # ── Expenses & Driver Salary ──
    total_expenses = pd.to_numeric(exp["Amount"], errors="coerce").fillna(0).sum() if not exp.empty else 0.0
    total_salary   = pd.to_numeric(sal["Salary"], errors="coerce").fillna(0).sum() if not sal.empty else 0.0

    st.markdown("#### 🧾 Expenses & Driver Salary")
    e1, e2 = st.columns(2)
    e1.metric("Vehicle Expenses", f"₹{total_expenses:,.0f}")
    e2.metric("Driver Salary Paid", f"₹{total_salary:,.0f}")

    # ── Overall Net — Final Payment me se diesel cost, expenses, aur driver
    # salary bhi minus karke ek poora "sab kuch mila ke" bottom-line dikhata
    # hai (Quick Overview ke simple "Net" — Payment−Diesel — se zyada complete) ──
    overall_net = final_payment - total_diesel_cost - total_expenses - total_salary
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#14A085,#7B8CFF);border-radius:12px;
                padding:20px;text-align:center;margin-top:12px;'>
        <span style='color:#fff;font-size:0.9rem;'>Overall Net (Final Payment − Diesel − Expenses − Driver Salary)</span><br>
        <span style='color:#FFD700;font-size:1.8rem;font-weight:800;'>₹{overall_net:,.0f}</span>
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
