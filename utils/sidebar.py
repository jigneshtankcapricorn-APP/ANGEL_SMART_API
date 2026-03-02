"""
Shared sidebar and auth helpers used by every page.
Import and call render_sidebar() at the top of each page.
"""
import streamlit as st
from datetime import datetime, time as dtime
import pytz


def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)


def require_app_login():
    """Redirect to login page if not authenticated."""
    if not st.session_state.get("app_authenticated"):
        st.warning("🔐 Please login first.")
        st.page_link("pages/0_Login.py", label="Go to Login →", icon="🔐")
        st.stop()


def render_sidebar():
    """Render the standard sidebar on every page."""
    ist = pytz.timezone('Asia/Kolkata')

    # Init session keys
    for k in ['connected', 'angel_obj', 'user_data', 'app_authenticated']:
        if k not in st.session_state:
            st.session_state[k] = False if k in ('connected', 'app_authenticated') else None

    with st.sidebar:
        st.title("📊 Angel One")
        st.caption(datetime.now(ist).strftime('%d %b %Y %H:%M IST'))
        st.divider()

        if market_open():
            st.success("🟢 MARKET OPEN")
        else:
            st.error("🔴 MARKET CLOSED")
        st.divider()

        if not st.session_state.connected:
            st.subheader("🔑 Angel One API")
            if st.button("🔴 CONNECT TO ANGEL ONE", use_container_width=True, type="primary"):
                from utils.angel_connect import connect_angel_one
                with st.spinner("Connecting…"):
                    obj, user = connect_angel_one()
                    if obj:
                        st.session_state.angel_obj = obj
                        st.session_state.user_data = user
                        st.session_state.connected = True
                        st.rerun()
        else:
            u = st.session_state.user_data or {}
            name = u.get('name') or u.get('clientName') or u.get('client_name') or 'Trader'
            st.success(f"✅ {name}")
            if st.button("🔌 Disconnect", use_container_width=True):
                from utils import data_store
                data_store.clear_all()
                for k in ['connected', 'angel_obj', 'user_data', 'watchlist_data', 'signals_data']:
                    st.session_state.pop(k, None)
                st.rerun()

        st.divider()

        # App logout
        if st.button("🚪 Logout App", use_container_width=True):
            from utils import data_store
            data_store.clear_all()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.switch_page("pages/0_Login.py")

        st.caption("Built with Angel One SmartAPI")

    return market_open()
