import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(
    page_title="Vehicle Management",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

from src.screens.home_page import home_page
from src.screens.driver_records import driver_records
from src.screens.expanses import expenses
from src.screens.vehicle_records import vehicle_records
from src.screens.access_manager import access_manager_page
from src.vehicle_records.vehicle_0303 import page_0303, expense_0303
from src.vehicle_records.vehicle_31 import page_3131, expense_3131
from src.vehicle_records.vehicle_89 import page_7389, expense_7389
from src.vehicle_records.vehicle_50 import page_2350, expense_2350
from src.database.auth import (
    login_page, logout, is_logged_in,
    get_current_role, get_accessible_vehicles, is_admin_or_manager
)


def main():
    if 'login_state' not in st.session_state:
        st.session_state['login_state'] = None

    # Login check
    if not is_logged_in():
        login_page()
        return

    # Logout + role badge sidebar mein
    logout()

    # Access Manager button — sirf admin/manager ko
    if is_admin_or_manager():
        with st.sidebar:
            if st.button("👥 Access Manager", use_container_width=True):
                st.session_state['login_state'] = 'access_manager'
                st.rerun()

    # ── Routing ──
    match st.session_state['login_state']:

        case 'access_manager':
            access_manager_page()

        case 'vehicle_record':
            vehicle_records()

        case 'driver_record':
            driver_records()

        case 'expenses':
            expenses()

        # ── Vehicle pages — access check ──
        case 'page_0303':
            if '0303' in get_accessible_vehicles():
                page_0303()
            else:
                st.error("❌ You don't have access.Contact Admin.")    

        case 'page_2350':
            if '2350' in get_accessible_vehicles():
                page_2350()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case 'page_7389':
            if '7389' in get_accessible_vehicles():
                page_7389()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case 'page_3131':
            if '3131' in get_accessible_vehicles():
                page_3131()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case '3131_E':
            if '3131' in get_accessible_vehicles():
                expense_3131()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case '0303_E':
            if '0303' in get_accessible_vehicles():
                expense_0303()
            else:
                sst.error("❌ You don't have access.Contact Admin.")

        case '7389_E':
            if '7389' in get_accessible_vehicles():
                expense_7389()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case '2350_E':
            if '2350' in get_accessible_vehicles():
                expense_2350()
            else:
                st.error("❌ You don't have access.Contact Admin.")

        case None:
            home_page()


main()
