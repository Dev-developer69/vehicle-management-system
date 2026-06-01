import streamlit as st
from src.ui.home_base_layout import home_layout,image_backgroung

def home_page():
    st.header("Welcome to Vehicle Records ")
    home_layout()
    image_backgroung()
    st.text('Choose one')
    col1,col2 ,col3= st.columns(3, gap='small')
    with col1:
        if st.button("Vehicle Records",type='primary',key='btn1', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='vehicle_record'
            st.rerun()
    
    with col2:
        if st.button("Driver Records",type='primary',key='btn2', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='driver_record'
            st.rerun()
        
    with col3:
        if st.button("Expenses",type='primary',key='btn3', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='expenses'
            st.rerun()