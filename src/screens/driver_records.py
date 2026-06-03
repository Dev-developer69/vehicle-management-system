import streamlit as st
import pandas as pd
from src.ui.home_base_layout import home_layout
from src.database.db import get_salary_check


def driver_records():
    if st.button('Home page',type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
        st.session_state['login_state']= None
        st.rerun()
    home_layout()
    salary_check_view()


def salary_check_view():
    st.markdown("### Salary Check 📊")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        from_date = st.date_input("From", value=None, key="sc_from", format="YYYY-MM-DD")
    with col2:
        to_date = st.date_input("To", value=None, key="sc_to", format="YYYY-MM-DD")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Load", key="sc_load", type='primary', width='stretch'):
            st.session_state["salary_check_df"] = get_salary_check(
                from_date=str(from_date) if from_date else None,
                to_date=str(to_date) if to_date else None,
            )

    if "salary_check_df" in st.session_state:
        df = st.session_state["salary_check_df"]
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No data found.")