import streamlit as st
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.screens.home_page import home_page
from src.screens.driver_records import driver_records
from src.screens.expanses import expenses
from src.screens.vehicle_records import vehicle_records
from src.vehicle_records.vehicle_0303 import page_0303, expense_0303
from src.vehicle_records.vehicle_31 import page_3131, expense_3131
from src.vehicle_records.vehicle_89 import page_7389, expense_7389
from src.vehicle_records.vehicle_50 import page_2350, expense_2350
from src.database.auth import login_page, logout, is_logged_in


def main():
    if 'login_state' not in st.session_state:
        st.session_state['login_state'] = None

    #  Login check — agar logged in nahi toh sirf login page dikhao
    if not is_logged_in():
        login_page()
        return

    #  Logged in — logout button sidebar mein
    logout()

    match st.session_state['login_state']:
        case 'vehicle_record':
            vehicle_records()
        case 'driver_record':
            driver_records()
        case 'expenses':
            expenses()
        case 'page_0303':
            page_0303()
        case 'page_2350':
            page_2350()
        case 'page_7389':
            page_7389()
        case 'page_3131':
            page_3131()
        case '3131_E':
            expense_3131()
        case '0303_E':
            expense_0303()
        case '7389_E':
            expense_7389()
        case '2350_E':
            expense_2350()
        case None:
            home_page()


main()
