import streamlit as st
from src.database.config import supabase


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

        if st.button("Login", type="primary", width="stretch"):
            if not email or not password:
                st.warning("⚠️ Email aur password dono bharo.")
                return

            try:
                res = supabase.auth.sign_in_with_password({
                    "email":    email,
                    "password": password,
                })
                # Session store karo
                st.session_state["user"]         = res.user
                st.session_state["access_token"] = res.session.access_token
                st.session_state["login_state"]  = None  # home pe bhejo
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


def logout():
    """Sidebar mein logout button"""
    with st.sidebar:
        user = st.session_state.get("user")
        if user:
            st.markdown(f"👤 **{user.email}**")
            st.divider()
        if st.button("🚪 Logout", width="stretch"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            # Session clear
            for key in ["user", "access_token", "login_state"]:
                st.session_state.pop(key, None)
            st.rerun()


def is_logged_in() -> bool:
    """Check karo user logged in hai ya nahi"""
    return "user" in st.session_state and st.session_state["user"] is not None