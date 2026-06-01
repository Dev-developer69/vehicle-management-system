import streamlit as st
from src.ui.home_base_layout import home_layout

def expenses():
    col1, col2 = st.columns(2)
    with col1:
        st.header("Expenses ",text_alignment='center')
    with col2:
        if st.button('Home page',type='primary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()
    home_layout()

    col1, col2= st.columns(2, gap='small')
    with col1:
        if st.button("3131_Exp",type='secondary', width='stretch'):
            st.session_state['login_state']= '3131_E'
            st.rerun()

    with col2:
        if st.button("0303_Exp", type='secondary', width='stretch'):
            st.session_state['login_state']= '0303_E'
            st.rerun()
    
    with col1:
        if st.button("7389_Exp",type='secondary', width='stretch'):
            st.session_state['login_state']= '7389_E'
            st.rerun()

    with col2:
        if st.button("2350_Exp",type='secondary', width='stretch'):
            st.session_state['login_state']= '2350_E'
            st.rerun()