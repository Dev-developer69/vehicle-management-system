import streamlit as st
from src.ui.home_base_layout import home_layout, image_backgroung
from src.database.auth import get_current_role, is_admin_or_manager

def home_page():
    # ── Sidebar ──
    with st.sidebar:
        user = st.session_state.get("user")
        role = get_current_role()
        role_emoji = {"admin": "👑", "manager": "🧑‍💼", "subordinate": "👤"}.get(role, "👤")
        st.markdown(f"{role_emoji} **{user.email if user else ''}**")
        st.markdown(f"`{role.upper()}`")
        st.divider()

        if is_admin_or_manager():
            if st.button("👥 Access Manager", use_container_width=True):
                st.session_state['login_state'] = 'access_manager'
                st.rerun()

        if st.button("🚪 Logout", use_container_width=True):
            try:
                from src.database.config import supabase
                supabase.auth.sign_out()
            except Exception:
                pass
            for key in ["user", "access_token", "login_state", "role"]:
                st.session_state.pop(key, None)
            st.rerun()

    # ── Main page ──
    st.header("Welcome to Vehicle Records")
    home_layout()
    image_backgroung()
    st.text('Choose one')

    col1, col2, col3 = st.columns(3, gap='small')
    with col1:
        if st.button("Vehicle Records", type='secondary', key='btn1', width='stretch',
                     icon=':material/article:', icon_position='right'):
            st.session_state['login_state'] = 'vehicle_record'
            st.rerun()
    with col2:
        if st.button("Driver Records", type='secondary', key='btn2', width='stretch',
                     icon=':material/bus_railway:', icon_position='right'):
            st.session_state['login_state'] = 'driver_record'
            st.rerun()
    with col3:
        if st.button("Expenses", type='secondary', key='btn3', width='stretch',
                     icon=':material/payments:', icon_position='right'):
            st.session_state['login_state'] = 'expenses'
            st.rerun()

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
