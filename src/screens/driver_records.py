import calendar
import streamlit as st
import pandas as pd
from datetime import date
from src.ui.home_base_layout import home_layout
from src.database.db import get_salary_check, get_driver_salary
from src.database.auth import get_accessible_vehicles, get_current_role


def driver_records():
    if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state'] = None
        st.rerun()

    home_layout()
    salary_check_view()

    st.markdown("""
    <div style='position:fixed;bottom:20px;width:100%;text-align:center;color:white;font-size:0.9rem;'>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# SALARY CHECK VIEW
# ──────────────────────────────────────────────
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
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Total row
            total = {
                "Sr No": "",
                "Driver Name": "TOTAL",
                "Bus Number": "",
                "Duties": df["Duties"].sum(),
                "Salary Given": df["Salary Given"].sum(),
            }
            st.dataframe(pd.DataFrame([total]), use_container_width=True, hide_index=True)
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

            # ✅ FIX: sirf accessible vehicles ke drivers dikhao
            accessible = get_accessible_vehicles()
            bus_number = accessible[0] if accessible else ""
            df_sal = get_driver_salary(bus_number=bus_number)

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
            show_df = df.drop(columns=["id"], errors="ignore")
            st.dataframe(show_df, use_container_width=True, hide_index=True)

            # Total row
            total = {
                "Date": "",
                "Driver Name": "TOTAL",
                "Salary": df["Salary"].sum(),
                "Transaction": "",
            }
            st.dataframe(pd.DataFrame([total]), use_container_width=True, hide_index=True)
        else:
            st.info("No salary records found for this period.")
