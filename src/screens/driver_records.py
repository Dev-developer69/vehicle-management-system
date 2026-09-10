import calendar
import streamlit as st
import pandas as pd
from datetime import date
from src.ui.home_base_layout import home_layout

from src.database.auth import get_accessible_vehicles, get_current_role
from src.database.db import (
    get_salary_check, get_driver_salary, save_driver_salary,
    get_driver_rate, save_driver_rate, get_drivers_for_buses,
)



def _render_html_table(df: pd.DataFrame, total_row: dict = None):
    cols = list(df.columns)
    html = [
        "<div style='overflow-x:auto;border-radius:14px;"
        "border:1px solid rgba(123,140,255,0.35);"
        "box-shadow:0 4px 24px rgba(20,160,133,0.15), 0 0 0 1px rgba(255,255,255,0.03) inset;'>"
        "<table style='width:100%;border-collapse:collapse;color:#f0f0f0;font-size:0.88rem;'>"
    ]
    html.append("<thead><tr>")
    for c in cols:
        html.append(
            f"<th style='padding:12px 10px;text-align:left;white-space:nowrap;"
            f"background:linear-gradient(90deg,#14A085,#7B8CFF);color:#fff;"
            f"font-weight:700;letter-spacing:0.3px;'>{c}</th>"
        )
    html.append("</tr></thead><tbody>")

    for i, r in enumerate(df.to_dict("records")):
        row_bg = "#182838" if i % 2 == 0 else "#1E2B3D"
        html.append(f"<tr style='transition:background 0.2s;'>")
        for c in cols:
            val = r.get(c, "")
            val = "" if pd.isna(val) else val
            html.append(
                f"<td style='border-bottom:1px solid rgba(123,140,255,0.12);padding:10px;"
                f"white-space:nowrap;background:{row_bg};color:#eee;'>{val}</td>"
            )
        html.append("</tr>")

    if total_row:
        html.append(
            "<tr style='background:linear-gradient(90deg,rgba(20,160,133,0.35),rgba(123,140,255,0.35));'>"
        )
        for c in cols:
            val = total_row.get(c, "")
            html.append(
                f"<td style='padding:12px 10px;white-space:nowrap;"
                f"color:#FFD700;font-weight:800;font-size:0.95rem;"
                f"text-shadow:0 0 8px rgba(255,215,0,0.35);'>{val}</td>"
            )
        html.append("</tr>")

    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def driver_records():
    if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()

    home_layout()

    if "driver_records_view" not in st.session_state:
        st.session_state["driver_records_view"] = "salary_check"

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📊 Salary Check", type='primary' if st.session_state["driver_records_view"] == "salary_check" else 'secondary',
                     use_container_width=True, key="btn_salary_check"):
            st.session_state["driver_records_view"] = "salary_check"
            st.rerun()
    with col2:
        if st.button("💵 Add Salary", type='primary' if st.session_state["driver_records_view"] == "add_salary" else 'secondary',
                     use_container_width=True, key="btn_add_salary"):
            st.session_state["driver_records_view"] = "add_salary"
            st.rerun()
    with col3:
        if st.button("⚙️ Set Rate", type='primary' if st.session_state["driver_records_view"] == "set_rate" else 'secondary',
                     use_container_width=True, key="btn_set_rate"):
            st.session_state["driver_records_view"] = "set_rate"
            st.rerun()

    st.markdown("---")

    if st.session_state["driver_records_view"] == "salary_check":
        salary_check_view()
    elif st.session_state["driver_records_view"] == "add_salary":
        add_driver_salary_view()
    else:
        set_driver_rate_view()

    st.markdown("""
    <div style='position:fixed;bottom:20px;width:100%;text-align:center;color:white;font-size:0.9rem;'>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>""", unsafe_allow_html=True)

#---------------------------------------------
# SALARY CHECK VIEW
# ---------------------------------------------
def salary_check_view():
    st.markdown("### Salary Check 📊")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda x: date(2000, x, 1).strftime("%B"),
            key="sc_month",
        )
    with col2:
        default_half = "1-15" if date.today().day <= 15 else "16-31"
        half = st.radio(
            "Period",
            ["1-15", "16-31"],
            index=0 if default_half == "1-15" else 1,
            horizontal=True,
            key="sc_half",
        )
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key="sc_load", type='primary', use_container_width=True):
            year = date.today().year
            if half == "1-15":
                from_date = f"{year}-{month:02d}-01"
                to_date   = f"{year}-{month:02d}-15"
            else:
                last_day  = calendar.monthrange(year, month)[1]
                from_date = f"{year}-{month:02d}-16"
                to_date   = f"{year}-{month:02d}-{last_day}"

            # Subordinate ke liye sirf assigned buses
            accessible = get_accessible_vehicles()
            st.session_state["salary_check_df"] = get_salary_check(
                from_date=from_date,
                to_date=to_date,
                bus_numbers=accessible,
            )

    if "salary_check_df" in st.session_state:
        df = st.session_state["salary_check_df"]
        if not df.empty:
            total = {
                "Sr No":        "",
                "Driver Name":  "TOTAL",
                "Bus Number":   "",
                "Duties":       int(df["Duties"].sum()),
                "Salary Due":   f"{df['Salary Due'].sum():,.0f}",
                "Salary Given": f"{df['Salary Given'].sum():,.0f}",
                "Remaining":    f"{df['Remaining'].sum():,.0f}",
            }
            _render_html_table(df, total_row=total)
        else:
            st.info("No data found.")

    st.markdown("---")

    # ──────────────────────────────────────────────
    # DRIVER SALARY RECORDS
    # ──────────────────────────────────────────────
    st.markdown("### Driver Salary Records 💰")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        sal_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda x: date(2000, x, 1).strftime("%B"),
            key="sal_month",
        )
    with col2:
        default_half2 = "1-15" if date.today().day <= 15 else "16-31"
        sal_half = st.radio(
            "Period",
            ["1-15", "16-31"],
            index=0 if default_half2 == "1-15" else 1,
            horizontal=True,
            key="sal_half",
        )
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key="sal_load", type='primary', use_container_width=True):
            year = date.today().year
            if sal_half == "1-15":
                sal_from = f"{year}-{sal_month:02d}-01"
                sal_to   = f"{year}-{sal_month:02d}-15"
            else:
                last_day = calendar.monthrange(year, sal_month)[1]
                sal_from = f"{year}-{sal_month:02d}-16"
                sal_to   = f"{year}-{sal_month:02d}-{last_day}"

            # ✅ sabhi accessible vehicles ke drivers dikhao (loop over each bus)
            accessible = get_accessible_vehicles()

            if accessible:
                all_dfs = [get_driver_salary(bus_number=bus) for bus in accessible]
                all_dfs = [d for d in all_dfs if not d.empty]
                df_sal = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame(
                    columns=["id", "Date", "Driver Name", "Salary", "Transaction", "Updated By"]
                )
            else:
                df_sal = get_driver_salary(bus_number="")  # admin/manager — sab dikhao

            if not df_sal.empty:
                df_sal["Date"] = pd.to_datetime(df_sal["Date"])
                df_sal = df_sal[
                    (df_sal["Date"] >= pd.Timestamp(sal_from)) &
                    (df_sal["Date"] <= pd.Timestamp(sal_to))
                ]
                df_sal["Date"] = df_sal["Date"].dt.strftime("%Y-%m-%d")

            st.session_state["sal_records_df"] = df_sal

    if "sal_records_df" in st.session_state:
        df = st.session_state["sal_records_df"]
        if not df.empty:
            show_df = df.drop(columns=["id", "Updated By"], errors="ignore")
            total = {
                "Date":        "",
                "Driver Name": "TOTAL",
                "Salary":      f"{df['Salary'].sum():,.0f}",
                "Transaction": "",
            }
            _render_html_table(show_df, total_row=total)
        else:
            st.info("No salary records found for this period.")



# ──────────────────────────────────────────────
# SET DRIVER SALARY RATE
# ──────────────────────────────────────────────
def set_driver_rate_view():
    st.markdown("### Set Driver Salary Rate ⚙️")

    accessible = get_accessible_vehicles()
    if not accessible:
        st.info("Koi accessible vehicle nahi mila.")
        return

    # ✅ Agar driver har vehicle ke liye same rate leta hai, to Bus Number
    # select karne ki zaroorat nahi — ek hi baar "Sabhi vehicles" rate set
    # ho jaayegi (Salary Check automatically fallback karega agar kisi
    # particular bus ki alag rate na mili ho).
    same_for_all = st.checkbox(
        "🚌 Sabhi vehicles ke liye same rate (Bus Number select nahi karna)",
        key="rate_same_all",
    )

    if same_for_all:
        bus_number = "ALL"
        drivers = get_drivers_for_buses(accessible)
    else:
        bus_number = st.selectbox("Bus Number", options=accessible, key="rate_bus")
        drivers = get_drivers_for_buses([bus_number])

    if not drivers:
        st.info("Koi driver nahi mila.")
        return

    driver_name = st.selectbox("Driver Name", options=drivers, key="rate_driver")

    current_rate = get_driver_rate(bus_number, driver_name)
    if same_for_all:
        st.caption(f"Current Rate (sabhi vehicles): ₹{current_rate:,.2f} / duty")
    else:
        st.caption(f"Current Rate: ₹{current_rate:,.2f} / duty")
        st.caption(
            "ℹ️ Agar is driver ki is bus ke liye koi specific rate set nahi hai, "
            "to 'Sabhi vehicles' wali rate (agar set ki hui ho) fallback ke taur "
            "par use hogi."
        )

    new_rate = st.number_input(
        "Rate (per duty)",
        min_value=0.0,
        value=float(current_rate),
        step=50.0,
        key="rate_input",
    )

    if st.button("💾 Save Rate", type='primary', key="save_rate_btn"):
        user = st.session_state.get("user")
        updated_by = user.email if user else "unknown"
        save_driver_rate(bus_number, driver_name, new_rate, updated_by)
        if same_for_all:
            st.success(f"{driver_name} ka rate ₹{new_rate:,.2f} SABHI vehicles ke liye set ho gaya.")
        else:
            st.success(f"{driver_name} ka rate ₹{new_rate:,.2f} bus {bus_number} ke liye set ho gaya.")
        st.rerun()
        
# ──────────────────────────────────────────────
# ADD DRIVER SALARY (payment entry)
# ──────────────────────────────────────────────
def add_driver_salary_view():
    st.markdown("### Add Driver Salary 💵")

    accessible = get_accessible_vehicles()
    if not accessible:
        st.info("Koi accessible vehicle nahi mila.")
        return

    bus_number = st.selectbox("Bus Number", options=accessible, key="add_sal_bus")

    # ✅ Sirf isi selected bus ke drivers
    drivers = get_drivers_for_buses([bus_number])

    if not drivers:
        st.info(f"Bus {bus_number} ke liye koi driver nahi mila.")
        return

    with st.form("add_salary_form", clear_on_submit=True):
        driver_name = st.selectbox("Driver Name", options=drivers, key="add_sal_driver")

        col1, col2 = st.columns(2)
        with col1:
            sal_date = st.date_input("Date", value=date.today(), key="add_sal_date")
        with col2:
            amount = st.number_input("Amount", min_value=0.0, step=100.0, key="add_sal_amount")

        transaction = st.radio("Transaction Type", ["Cash", "Online"], horizontal=True, key="add_sal_txn")

        submitted = st.form_submit_button("💾 Save Payment", type='primary', use_container_width=True)
        if submitted:
            if amount <= 0:
                st.error("Amount 0 se zyada hona chahiye.")
            else:
                df = pd.DataFrame([{
                    "Driver Name": driver_name,
                    "Date": str(sal_date),
                    "Salary": amount,
                    "Transaction": transaction.lower(),
                }])
                save_driver_salary(df, bus_number=bus_number)
                st.success(f"₹{amount:,.2f} {driver_name} ko diya gaya — record ho gaya.")
                st.rerun()
