import streamlit as st
from src.ui.excel_format import editable_grid

def page_7389():
    col1, col2 = st.columns(2)
    with col1:
            st.header("Vehicle No. 7389 ",text_alignment='center')
    with col2:
        if st.button('Home page',type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()

        if st.button('Back page', type='primary', width='stretch', icon=':material/home:', shortcut='control+enter'):
            st.session_state['login_state']= 'vehicle_record'
            st.rerun()

    editable_grid()


def expanse_7389():
    col1, col2 = st.columns(2)
    with col1:
            st.header("Expanse page 7389 ",text_alignment='center')
    with col2:
        if st.button('Home page',type='secondary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()

        if st.button('Back page', type='primary', width='stretch', icon=':material/home:', shortcut='control+enter'):
            st.session_state['login_state']= 'expanses'
            st.rerun()