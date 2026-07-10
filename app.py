import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(
    page_title="Vehicle Management",
    page_icon="🚌",
    layout="wide",
  #  initial_sidebar_state="expanded"
)

#from src.screens.home_page import home_page
from src.screens.driver_records import driver_records
from src.screens.expanses import expenses
from src.screens.vehicle_records import vehicle_records
from src.screens.access_manager import access_manager_page
from src.screens.maintenance_manager import maintenance_page
from src.vehicle_records.vehicle_0303 import page_0303, expense_0303
from src.vehicle_records.vehicle_31 import page_3131, expense_3131
from src.vehicle_records.vehicle_89 import page_7389, expense_7389
from src.vehicle_records.vehicle_50 import page_2350, expense_2350
from src.ui.excel_format import products_page
from src.database.auth import (
    login_page, is_logged_in, get_current_role,
    get_accessible_vehicles, is_admin_or_manager,
    get_maintenance_access,
)
from src.database.config import supabase
from src.screens.home_page import home_page

def inject_sidebar_shortcut():
    st.markdown("""
        <script>
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.code === 'Space') {
                e.preventDefault();
                const btn = window.parent.document.querySelector('[data-testid="collapsedControl"]') ||
                            window.parent.document.querySelector('[data-testid="baseButton-headerNoPadding"]');
                if (btn) btn.click();
            }
        });
        </script>
    """, unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        user = st.session_state.get("user")
        role = get_current_role()
        role_emoji = {"admin": "👑", "manager": "🧑‍💼", "subordinate": "👤"}.get(role, "👤")
        st.markdown(f"{role_emoji} **{user.email if user else ''}**")
        st.markdown(f"`{role.upper()}`")
        st.divider()

        if st.button("🏠 Home", key="sb_home", use_container_width=True):
            st.session_state['login_state'] = None
            st.rerun()

        st.divider()
        if st.button("🚪 Logout", key="sb_logout", use_container_width=True):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            for key in ["user", "access_token", "login_state", "role"]:
                st.session_state.pop(key, None)
            st.rerun()


def main():
    if 'login_state' not in st.session_state:
        st.session_state['login_state'] = None

    if not is_logged_in():
        login_page()
        return

    # Sidebar har page pe
    render_sidebar()
    inject_sidebar_shortcut()

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
        case 'page_0303':
            if '0303' in get_accessible_vehicles():
                page_0303()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case 'page_2350':
            if '2350' in get_accessible_vehicles():
                page_2350()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case 'page_7389':
            if '7389' in get_accessible_vehicles():
                page_7389()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case 'page_3131':
            if '3131' in get_accessible_vehicles():
                page_3131()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case '3131_E':
            if '3131' in get_accessible_vehicles():
                expense_3131()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case '0303_E':
            if '0303' in get_accessible_vehicles():
                expense_0303()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case '7389_E':
            if '7389' in get_accessible_vehicles():
                expense_7389()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case '2350_E':
            if '2350' in get_accessible_vehicles():
                expense_2350()
            else:
                st.error("❌ You don't have access. Contact Admin.")
        case 'products':

            role = get_current_role()
            user = st.session_state.get("user")
            # admin/manager ko by default access
            if role in ('admin', 'manager'):
                products_page()
            else:
                # subordinate ke liye products_access check karo
                res = supabase.table("user_roles").select("products_access") \
                    .eq("user_id", user.id).execute()
                has_access = bool(res.data[0].get("products_access", False)) if res.data else False
                if has_access:
                    products_page()
                else:
                    st.error("❌ Access denied..")

        case 'maintenance':
            if get_maintenance_access():
                maintenance_page()
            else:
                st.error("❌ Access denied..")
        case None:
            home_page()

main()
