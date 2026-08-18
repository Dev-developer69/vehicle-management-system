import streamlit as st
from src.database.config import supabase
from src.ui.home_base_layout import image_backgroung


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


ALL_VEHICLES = ["7389", "2350", "0303", "3131", "AT7389"]

def get_accessible_vehicles() -> list:
    """Subordinate ke liye assigned vehicles, admin/manager ko sab"""
    user = st.session_state.get("user")
    if not user:
        return []

    role = get_current_role()
    if role in ("admin", "manager"):
        return ALL_VEHICLES
    else:
        res = supabase.table("vehicle_access").select("bus_number").eq("user_id", user.id).execute()
        return [r["bus_number"] for r in res.data] if res.data else []


def is_admin_or_manager() -> bool:
    return get_current_role() in ("admin", "manager")


def get_product_access_flags() -> dict:
    """Current user ke product access flags fetch karo"""
    user = st.session_state.get("user")
    if not user:
        return {
            "products_access":   False,
            "products_view":     False,
            "suppliers_view":    False,
            "requirements_view": False,
        }
    # Admin/Manager ko sab access
    if is_admin_or_manager():
        return {
            "products_access":   True,
            "products_view":     True,
            "suppliers_view":    True,
            "requirements_view": True,
        }
    # Subordinate — DB se fetch karo
    res = supabase.table("user_roles") \
        .select("products_access, products_view, suppliers_view, requirements_view") \
        .eq("user_id", user.id) \
        .execute()
    if res.data:
        return {
            "products_access":   bool(res.data[0].get("products_access", False)),
            "products_view":     bool(res.data[0].get("products_view", False)),
            "suppliers_view":    bool(res.data[0].get("suppliers_view", False)),
            "requirements_view": bool(res.data[0].get("requirements_view", False)),
        }
    return {
        "products_access":   False,
        "products_view":     False,
        "suppliers_view":    False,
        "requirements_view": False,
    }

def get_maintenance_access() -> bool:
    """Current user ko Maintenance Manager access hai ya nahi"""
    user = st.session_state.get("user")
    if not user:
        return False
    # Admin/Manager ko hamesha access
    if is_admin_or_manager():
        return True
    # Subordinate — DB se fetch karo
    res = supabase.table("user_roles") \
        .select("maintenance_access") \
        .eq("user_id", user.id) \
        .execute()
    if res.data:
        return bool(res.data[0].get("maintenance_access", False))
    return False

# ──────────────────────────────────────────────
# LOGIN PAGE
# ──────────────────────────────────────────────
def login_page():
    image_backgroung(overlay_color="rgba(20, 35, 70, 0.72)")  # black ki jagah navy-blue tint

    st.markdown("""
        <style>
            [data-testid="stForm"] {
                background: rgba(15, 20, 40, 0.55);
                backdrop-filter: blur(14px);
                -webkit-backdrop-filter: blur(14px);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 18px;
                padding: 28px 24px 12px 24px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.35);
            }
            [data-testid="stForm"] button[kind="primary"] {
                background: linear-gradient(135deg, #7B8CFF 0%, #C566E8 100%) !important;
                border: none !important;
            }
            [data-testid="stForm"] button[kind="primary"]:hover {
                filter: brightness(1.1);
            }
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            #MainMenu {
                display: none !important;
                height: 0 !important;
                visibility: hidden !important;
            }
            [data-testid="stAppViewContainer"] {
                overflow: hidden !important;
            }
            html, body {
                overflow: hidden !important;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div style='text-align: center; padding: 40px 0 20px 0;'>
            <h1 style='color: white;'>🚌 Vehicle Maintenance</h1>
            <p style='color: rgba(255,255,255,0.65);'>Login to continue</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            email    = st.text_input("📧 Email", placeholder="you@example.com")
            password = st.text_input("🔒 Password", type="password", placeholder="••••••••")
            submit   = st.form_submit_button("Login", width='stretch', type="primary")

        if submit:
            if not email or not password:
                st.warning("⚠️ Email aur password dono bharo.")
            else:
                try:
                    res = supabase.auth.sign_in_with_password({
                        "email":    email,
                        "password": password,
                    })
                    st.session_state["user"]         = res.user
                    st.session_state["access_token"] = res.session.access_token
                    st.session_state["login_state"]  = None
                    st.session_state.pop("role", None)
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
        if st.button("🚪 Logout", width='stretch'):
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
