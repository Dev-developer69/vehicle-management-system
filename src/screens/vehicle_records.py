import streamlit as st
import pandas as pd
from src.ui.home_base_layout import home_layout
from src.database.auth import get_accessible_vehicles, is_admin_or_manager
# Bus number → session state key mapping
VEHICLE_MAP = {
    "7389": "page_7389",
    "2350": "page_2350",
    "0303": "page_0303",
    "3131": "page_3131",
}
def vehicle_records():
    col1, col2 = st.columns(2)
    with col1:
        st.header("Select Vehicle", text_alignment='center')
    with col2:
        if st.button('Home page', type='primary', width='stretch', icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state'] = None
            st.rerun()
    home_layout()
    # Sirf accessible vehicles ke buttons dikhao
    accessible = get_accessible_vehicles()
    visible_vehicles = [bus for bus in VEHICLE_MAP.keys() if bus in accessible]
    if not visible_vehicles:
        st.warning("⚠️ Aapko kisi bhi vehicle ka access nahi diya gaya. Admin se contact karo.")
    else:
        # 2 columns mein buttons
        cols = st.columns(2)
        for i, bus in enumerate(visible_vehicles):
            with cols[i % 2]:
                btn_type = 'secondary' if i < 2 else 'tertiary'
                if st.button(
                    bus,
                    type=btn_type,
                    key=f"btn_v_{bus}",
                    width='stretch',
                    icon=':material/bus_railway:',
                    icon_position='right'
                ):
                    st.session_state['login_state'] = VEHICLE_MAP[bus]
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
    stats_df = pd.DataFrame({
        "icon":  ["🚗", "🔧", "✅", "⏳"],
        "label": ["Total Vehicles", "Under Maintenance", "Completed Jobs", "Pending Jobs"],
        "value": [120, 35, 85, 12],
    })
    cols = st.columns(4)
    for col, (_, row) in zip(cols, stats_df.iterrows()):
        with col:
            st.markdown(f"""
                <div style="
                    background: #14A085;
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

