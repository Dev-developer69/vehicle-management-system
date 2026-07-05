import streamlit as st
from src.database.config import supabase, supabase_admin
from src.database.auth import get_current_role, is_admin_or_manager
from src.ui.home_base_layout import home_layout


# ══════════════════════════════════════════════
# DB HELPERS
# ══════════════════════════════════════════════
def _get_all_users():
    res = supabase.table("user_roles").select("*").execute()
    return res.data or []


def _get_all_vehicles():
    return ["7389", "2350", "0303", "3131"]


def _get_user_vehicles(user_id: str):
    res = supabase.table("vehicle_access").select("bus_number").eq("user_id", user_id).execute()
    return [r["bus_number"] for r in res.data] if res.data else []


def _grant_access(user_id: str, bus_number: str, granted_by: str):
    supabase.table("vehicle_access").upsert({
        "user_id":    user_id,
        "bus_number": bus_number,
        "granted_by": granted_by,
    }, on_conflict="user_id,bus_number").execute()


def _revoke_access(user_id: str, bus_number: str):
    supabase.table("vehicle_access").delete()\
        .eq("user_id", user_id)\
        .eq("bus_number", bus_number)\
        .execute()


def _add_user(email: str, password: str, role: str):
    res = supabase_admin.auth.admin.create_user({
        "email":         email,
        "password":      password,
        "email_confirm": True,
    })
    user_id = res.user.id
    supabase.table("user_roles").upsert({
        "user_id":           user_id,
        "email":             email,
        "role":              role,
        "products_access":   False,
        "products_view":     False,
        "suppliers_view":    False,
        "requirements_view": False,
    }, on_conflict="user_id").execute()
    return user_id


def _delete_user(user_id: str):
    supabase_admin.auth.admin.delete_user(user_id)
    supabase.table("user_roles").delete().eq("user_id", user_id).execute()
    supabase.table("vehicle_access").delete().eq("user_id", user_id).execute()


def _update_role(user_id: str, new_role: str):
    supabase.table("user_roles").update({"role": new_role}).eq("user_id", user_id).execute()


def _get_product_access_flags(user_id: str) -> dict:
    res = supabase.table("user_roles") \
        .select("products_access, products_view, suppliers_view, requirements_view") \
        .eq("user_id", user_id).execute()
    if res.data:
        return {
            "products_access":   bool(res.data[0].get("products_access", False)),
            "products_view":     bool(res.data[0].get("products_view", False)),
            "suppliers_view":    bool(res.data[0].get("suppliers_view", False)),
            "requirements_view": bool(res.data[0].get("requirements_view", False)),
        }
    return {
        "products_access": False, "products_view": False,
        "suppliers_view": False,  "requirements_view": False,
    }


def _set_product_access_flags(user_id: str, flags: dict):
    supabase.table("user_roles").update(flags).eq("user_id", user_id).execute()


# ══════════════════════════════════════════════
# ACCESS MANAGER PAGE
# ══════════════════════════════════════════════

def access_manager_page():
    home_layout()
    col1, col2 = st.columns(2)
    with col1:
        if st.button('Home page', type='secondary', width='stretch',
                     icon=':material/home:', shortcut='control+backspace'):
            st.session_state['login_state'] = None
            st.rerun()

    if not is_admin_or_manager():
        st.error("❌ Access denied. Admin ya Manager hi yeh page dekh sakte hain.")
        return

    role         = get_current_role()
    current_user = st.session_state.get("user")

    st.markdown("## 👥 Access Manager")

    tab1, tab2 = st.tabs(["🧑‍💼 Users & Roles", "🚌 Vehicle Access"])

    # ── TAB 1: Users & Roles ──
    with tab1:
        st.markdown("### All Users")
        users = _get_all_users()

        if not users:
            st.info("Koi user nahi mila. Pehle user add karo.")
        else:
            for u in users:
                with st.expander(f"{u['email']}  —  `{u['role'].upper()}`"):
                    if role == "admin":
                        new_role = st.selectbox(
                            "Role",
                            ["admin", "manager", "subordinate"],
                            index=["admin", "manager", "subordinate"].index(u["role"]),
                            key=f"role_{u['user_id']}",
                        )
        st.divider()
        st.markdown("### ➕ Add New User")
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    new_email = st.text_input("Email", key="new_email")
with c2:
    new_pass = st.text_input("Password", type="password", key="new_pass")
with c3:
    if role == "admin":
        new_role = st.selectbox("Role", ["subordinate", "manager", "admin"], key="new_role")
    else:
        new_role = "subordinate"
        st.markdown("<br>**Role:** Subordinate", unsafe_allow_html=True)

if st.button("➕ Create User", type="primary"):
    if not new_email or not new_pass:
        st.warning("⚠️ Email aur password bharo.")
    else:
        try:
            uid = _add_user(new_email, new_pass, new_role)
            st.success(f"✅ User `{new_email}` created as `{new_role}`!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {e}")
    # ── TAB 2: Vehicle Access ──

    with tab2:
        st.markdown("### Assign Vehicles & Access to Subordinates")

        users     = _get_all_users()
        subs      = [u for u in users if u["role"] == "subordinate"]
        all_buses = _get_all_vehicles()

        if not subs:
            st.info("Koi subordinate nahi hai. Pehle user add karo.")
            return

        for u in subs:
            with st.expander(f"🧑 {u['email']}"):

                # ── Vehicle Access ──
                st.markdown("**🚌 Vehicle Access**")
                current_buses = _get_user_vehicles(u["user_id"])
                c1, c2 = st.columns([3, 1])
                with c1:
                    to_grant = st.multiselect(
                        "Vehicles assign karo",
                        options=all_buses,
                        default=current_buses,
                        key=f"va_{u['user_id']}",
                    )

                st.markdown("---")

                # ── Products Access ──
                st.markdown("**📦 Products Manager Access**")
                flags = _get_product_access_flags(u["user_id"])

                pa = st.checkbox(
                    "Products Manager khol sakte hain",
                    value=flags["products_access"],
                    key=f"pa2_{u['user_id']}",
                )
                if pa:
                    pc1, pc2, pc3 = st.columns(3)
                    with pc1:
                        pv = st.checkbox("🛒 Product Details",
                                        value=flags["products_view"],
                                        key=f"pv2_{u['user_id']}")
                    with pc2:
                        sv = st.checkbox("🏭 Supplier Details",
                                        value=flags["suppliers_view"],
                                        key=f"sv2_{u['user_id']}")
                    with pc3:
                        rv = st.checkbox("📋 Requirements",
                                        value=flags["requirements_view"],
                                        key=f"rv2_{u['user_id']}")
                else:
                    pv = sv = rv = False

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 Save All", key=f"save_va_{u['user_id']}", 
                            type="primary", use_container_width=True):
                    # Vehicle access save
                    for bus in to_grant:
                        if bus not in current_buses:
                            _grant_access(u["user_id"], bus, current_user.id)
                    for bus in current_buses:
                        if bus not in to_grant:
                            _revoke_access(u["user_id"], bus)

                    # Products access save
                    _set_product_access_flags(u["user_id"], {
                        "products_access":   pa,
                        "products_view":     pv,
                        "suppliers_view":    sv,
                        "requirements_view": rv,
                    })
                    st.success("✅ Access updated!")
                    st.rerun()