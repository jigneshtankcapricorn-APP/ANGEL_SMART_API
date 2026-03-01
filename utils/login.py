"""
utils/login.py
Shared login sidebar — imported by EVERY page.
This ensures session persists and login is always available.
"""
import streamlit as st
from datetime import datetime
import pytz


def is_market_open() -> bool:
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    from datetime import time as dt_time
    return dt_time(9, 15) <= now.time() <= dt_time(15, 30)


def format_dt() -> str:
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%d %b %Y  %H:%M IST')


def render_sidebar():
    """
    Call this at the TOP of every page.
    Renders login + navigation in sidebar.
    Returns True if connected, False if not.
    """
    # ── Init session keys ─────────────────────────────────────────
    for key in ['connected', 'angel_obj', 'user_data']:
        if key not in st.session_state:
            st.session_state[key] = False if key == 'connected' else None

    with st.sidebar:
        st.markdown("## 📊 Angel One Trading")
        st.caption(format_dt())
        st.markdown("---")

        if is_market_open():
            st.success("🟢 MARKET OPEN")
        else:
            st.error("🔴 MARKET CLOSED")

        st.markdown("---")

        # ── Login / Disconnect ────────────────────────────────────
        if not st.session_state.connected:
            st.markdown("### 🔑 Login")
            if st.button("🔴 CONNECT TO ANGEL ONE",
                         use_container_width=True, type="primary",
                         key="sidebar_login_btn"):
                _do_login()
        else:
            user = st.session_state.user_data or {}
            name = (user.get('name') or user.get('clientName') or
                    user.get('client_name') or 'Connected')
            st.success(f"✅ {name}")
            if st.button("🔌 Disconnect", use_container_width=True,
                         key="sidebar_disconnect_btn"):
                for k in ['connected', 'angel_obj', 'user_data',
                          'watchlist_data', 'signals_data']:
                    st.session_state.pop(k, None)
                st.rerun()

        st.markdown("---")
        st.markdown("**🗂 Pages**")
        # Streamlit auto-renders page links from pages/ folder here
        st.markdown("---")
        st.caption("Angel One SmartAPI + Streamlit")

    return st.session_state.connected


def _do_login():
    """Perform Angel One login and store in session state."""
    try:
        from utils.angel_connect import connect_angel_one
        with st.spinner("Connecting to Angel One…"):
            obj, user = connect_angel_one()
            if obj:
                st.session_state.angel_obj = obj
                st.session_state.user_data = user
                st.session_state.connected = True
                st.rerun()
    except Exception as e:
        st.error(f"❌ Login failed: {e}")


def require_login():
    """
    Call at top of any page that needs login.
    Shows login form inline if not connected, then stops page.
    """
    for key in ['connected', 'angel_obj', 'user_data']:
        if key not in st.session_state:
            st.session_state[key] = False if key == 'connected' else None

    if not st.session_state.connected:
        st.warning("🔑 Please **Connect to Angel One** using the sidebar to access this page.")

        # Show inline login button as backup
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔴 CONNECT TO ANGEL ONE",
                         use_container_width=True, type="primary",
                         key="inline_login_btn"):
                _do_login()
        st.stop()
