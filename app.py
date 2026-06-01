import streamlit as st

from src.screens.home_page import home_page
from src.screens.driver_records import driver_records
from src.screens.expanses import expanses
from src.screens.vehicle_records import vehicle_records
from src.vehicle_records.vehicle_0303 import page_0303, expanse_0303
from src.vehicle_records.vehicle_31 import page_3131, expanse_3131
from src.vehicle_records.vehicle_89 import page_7389, expanse_7389
from src.vehicle_records.vehicle_50 import page_2350, expanse_2350

def main():


    if 'login_state' not in st.session_state:
        st.session_state['login_state'] = None


    match st.session_state['login_state']:
        case 'vehicle_record':
            vehicle_records()

        case 'driver_record':
            driver_records()

        case 'expanses':
            expanses()

        case 'page_0303':
            page_0303()

        case 'page_2350':
            page_2350()

        case 'page_7389':
            page_7389()

        case 'page_3131':
            page_3131()

        case '3131_E':
            expanse_3131()

        case '0303_E':
            expanse_0303()

        case '7389_E':
            expanse_7389()

        case '2350_E':
            expanse_2350()
        case None:
            home_page()


main()