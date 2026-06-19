import streamlit as st
from src.ui.excel_format import editable_grid, driver_salary, expenses, diesel_view
from src.ui.home_base_layout import background,home_layout

def page_0303():
    home_layout()
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Home page',type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()
        
    with col2:
        if st.button('Back page', type='primary', width='stretch', icon=':material/home:', shortcut='control+enter'):
            st.session_state['login_state']= 'vehicle_record'
            st.rerun()

    editable_grid(bus_number='0303')

def expense_0303():

    background()
    st.header("Expense page 0303 ", text_alignment='center')
    col1, col2 = st.columns(2)

    with col1:
        if st.button('Home page', type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()

    with col2:
        if st.button('Back page',type='primary', width='stretch', icon=':material/home:', shortcut='control+enter'):
            st.session_state['login_state']= 'expenses'
            st.rerun()

    if 'expense_tab' not in st.session_state:
        st.session_state['expense_tab'] = None

    if st.button('Vehicle Expense',type='tertiary', width='stretch', icon=':material/home:'):
        st.session_state['expense_tab'] = 'vehicle'

    if st.button('Driver Salary',type='tertiary', width='stretch', icon=':material/home:'):
        st.session_state['expense_tab'] = 'driver'
    
    if st.button('Diesel View', type='tertiary', width='stretch', icon=':material/local_gas_station:'):
        st.session_state['expense_tab'] = 'diesel'


    if st.session_state['expense_tab'] == 'vehicle':
        expenses(bus_number='0303')
    elif st.session_state['expense_tab'] == 'driver':
        driver_salary(bus_number='0303')
    elif st.session_state['expense_tab'] == 'diesel':
        diesel_view(bus_number='0303')
