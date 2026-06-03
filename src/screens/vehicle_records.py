import streamlit as st
import pandas as pd
from src.ui.home_base_layout import home_layout

def vehicle_records():
    col1, col2 = st.columns(2)
    with col1:
        st.header("Select Vehicle ",text_alignment='center')
    with col2:
        if st.button('Home page',type='primary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state']= None
            st.rerun()
    home_layout()

    col1,col2 = st.columns(2)
    with col1:
        if st.button("7389",type='secondary',key='btn1', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='page_7389'
            st.rerun()
    
    with col2:
        if st.button("2350",type='secondary',key='btn2', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='page_2350'
            st.rerun()
        
    with col1:
        if st.button("0303",type='tertiary',key='btn3', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='page_0303'
            st.rerun()

    with col2:
        if st.button("3131",type='tertiary',key='btn4', width= 'stretch', icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state']='page_3131'
            st.rerun()

    stats_grid()

    st.markdown("""
    <div style='
        position: fixed;
        bottom: 20px;
        width: 100%;
        text-align: center;
        color: white;
        font-size: 0.9rem;
    '>
        <p>Created with ❤️ by Dev-developer69</p>
    </div>
""", unsafe_allow_html=True)
    

def stats_grid():
    # ✅ Store stats in a DataFrame — easy to update
    stats_df = pd.DataFrame({
        "icon":  ["🚗", "🔧", "✅", "⏳"],
        "label": ["Total Vehicles", "Under Maintenance", "Completed Jobs", "Pending Jobs"],
        "value": [120, 35, 85, 12],  # numbers so they can be calculated
    })

    cols = st.columns(4)

    for col, (_, row) in zip(cols, stats_df.iterrows()):
        with col:
            st.markdown(f"""
                <div style="
                    background: rgba(255,255,255,0.15);
                    border-radius: 12px;
                    padding: 20px;
                    text-align: center;
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.3);
                    opacity:0.7;
                ">
                    <h2 style="font-size:2rem; margin:0;">{row['icon']}</h2>
                    <h3 style="font-size:1.8rem; margin:5px 0; color:white;">{row['value']}</h3>
                    <p style="color:rgba(255,255,255,0.8); margin:0;">{row['label']}</p>
                </div>
            """, unsafe_allow_html=True)

