import streamlit as st
from src.database.config import supabase


# ──────────────────────────────────────────────
# ROLE HELPERS
# ──────────────────────────────────────────────
def get_current_role() -> str:
    """Returns: 'admin' | 'manager' | 'subordinate' | 'unknown'"""
    user = st.session_state.get("user")
    if not user:
        return "unknown"
    role_data = st.session_state.get("role")
    if role_data:
        return role_data
    # fetch from DB
    res = supabase.table("user_roles").select("role").eq("user_id", user.id).execute()
    role = res.data[0]["role"] if res.data else "subordinate"
    st.session_state["role"] = role
    return role


def get_accessible_vehicles() -> list:
    """Subordinate ke liye assigned vehicles, admin/manager ko sab"""
    user = st.session_state.get("user")
    if not user:
        return []

    role = get_current_role()
    if role in ("admin", "manager"):
        # sab vehicles
        res = supabase.table("vehicle_records").select("bus_number").execute()
        buses = list({r["bus_number"] for r in res.data}) if res.data else []
        return sorted(buses)
    else:
        # sirf assigned vehicles
        res = supabase.table("vehicle_access").select("bus_number").eq("user_id", user.id).execute()
        return [r["bus_number"] for r in res.data] if res.data else []


def is_admin_or_manager() -> bool:
    return get_current_role() in ("admin", "manager")


# ──────────────────────────────────────────────
# LOGIN PAGE
# ──────────────────────────────────────────────
def login_page():
    st.markdown("""
        <div style='text-align: center; padding: 40px 0 20px 0;'>
            <h1>🚌 Vehicle Maintenance</h1>
            <p style='color: gray;'>Login to continue</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        email    = st.text_input("📧 Email", placeholder="you@example.com")
        password = st.text_input("🔒 Password", type="password", placeholder="••••••••")

        if st.button("Login", type="primary", use_container_width=True):
            if not email or not password:
                st.warning("⚠️ Email aur password dono bharo.")
                return
            try:
                res = supabase.auth.sign_in_with_password({
                    "email":    email,
                    "password": password,
                })
                st.session_state["user"]         = res.user
                st.session_state["access_token"] = res.session.access_token
                st.session_state["login_state"]  = None
                st.session_state.pop("role", None)  # fresh fetch on next load
                st.rerun()
            except Exception as e:
                err = str(e).lower()
                if "invalid" in err or "credentials" in err:
                    st.error("❌ Email ya password galat hai.")
                elif "email not confirmed" in err:
                    st.error("❌ Email confirm nahi hua — inbox check karo.")
                else:
                    st.error(f"❌ Error: {e}")

        st.markdown("""
            <div style='text-align:center; margin-top: 20px; color: gray; font-size: 0.85rem;'>
                Doesn't have account? Contact Admin.
            </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# LOGOUT
# ──────────────────────────────────────────────
def logout():
    """Sidebar mein logout button"""
    with st.sidebar:
        user = st.session_state.get("user")
        role = get_current_role()
        if user:
            role_emoji = {"admin": "👑", "manager": "🧑‍💼", "subordinate": "👤"}.get(role, "👤")
            st.markdown(f"{role_emoji} **{user.email}**")
            st.markdown(f"`{role.upper()}`")
            st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            for key in ["user", "access_token", "login_state", "role"]:
                st.session_state.pop(key, None)
            st.rerun()


# ──────────────────────────────────────────────
# IS LOGGED IN
# ──────────────────────────────────────────────
def is_logged_in() -> bool:
    return "user" in st.session_state and st.session_state["user"] is not None
