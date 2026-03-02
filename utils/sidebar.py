"""
Shared sidebar and auth helpers used by every page.
FIXES:
- Auto-reconnect when Angel One session expires (mobile screen off / app switch)
- Manual Reconnect button in sidebar
- Session timestamp display
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


def _try_reconnect_silent():
    """Silently attempt to reconnect to Angel One. Returns True if OK."""
    try:
        from utils.angel_connect import connect_angel_one
        obj, user = connect_angel_one()
        if obj:
            st.session_state.angel_obj = obj
            st.session_state.user_data = user
            st.session_state.connected = True
            st.session_state["_last_reconnect"] = datetime.now().isoformat()
            return True
    except Exception:
        pass
    st.session_state.connected = False
    return False


def check_session_alive():
    """
    Call before any Angel One API operation.
    Auto-reconnects if session has expired.
    Returns True if session is alive/restored, False if failed.
    """
    if not st.session_state.get("connected"):
        return False
    if st.session_state.get("angel_obj") is None:
        return _try_reconnect_silent()

    # Rate-limit checks: only test session every 5 minutes
    last_check = st.session_state.get("_session_last_check")
    now = datetime.now()
    if last_check:
        try:
            elapsed = (now - datetime.fromisoformat(last_check)).total_seconds()
            if elapsed < 300:
                return True
        except Exception:
            pass

    # Lightweight session probe
    try:
        obj = st.session_state.angel_obj
        refresh_token = (st.session_state.get("user_data") or {}).get("refreshToken", "")
        profile = obj.getProfile(refresh_token)
        if profile and profile.get("status"):
            st.session_state["_session_last_check"] = now.isoformat()
            return True
    except Exception:
        pass

    # Session dead — auto-reconnect
    if _try_reconnect_silent():
        st.session_state["_session_last_check"] = now.isoformat()
        st.toast("🔄 Auto-reconnected to Angel One", icon="✅")
        return True
    return False


def render_sidebar():
    """Render the standard sidebar on every page."""
    ist = pytz.timezone('Asia/Kolkata')

    for k in ['connected', 'angel_obj', 'user_data', 'app_authenticated']:
        if k not in st.session_state:
            st.session_state[k] = False if k in ('connected', 'app_authenticated') else None

    # ── Background recovery: if was connected but obj is gone ──────
    if st.session_state.get("connected") and st.session_state.get("angel_obj") is None:
        with st.spinner("🔄 Session lost — reconnecting…"):
            if _try_reconnect_silent():
                st.toast("✅ Session restored automatically", icon="🔄")
            else:
                st.warning("⚠️ Session expired. Please reconnect from sidebar.")

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
                        st.session_state["_last_reconnect"] = datetime.now().isoformat()
                        st.rerun()
        else:
            u = st.session_state.user_data or {}
            name = u.get('name') or u.get('clientName') or u.get('client_name') or 'Trader'
            st.success(f"✅ {name}")

            last_rc = st.session_state.get("_last_reconnect")
            if last_rc:
                try:
                    rc_time = datetime.fromisoformat(last_rc)
                    st.caption(f"🔗 Session: {rc_time.strftime('%H:%M:%S')}")
                except Exception:
                    pass

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Reconnect", use_container_width=True,
                             help="Force a fresh Angel One session (use if data stops)"):
                    with st.spinner("Reconnecting…"):
                        if _try_reconnect_silent():
                            st.toast("✅ Reconnected!", icon="🔄")
                            st.rerun()
                        else:
                            st.error("❌ Reconnect failed. Check API credentials.")
            with col2:
                if st.button("🔌 Disconnect", use_container_width=True):
                    from utils import data_store
                    data_store.clear_all()
                    for k in ['connected', 'angel_obj', 'user_data',
                              'watchlist_data', 'signals_data',
                              '_last_reconnect', '_session_last_check']:
                        st.session_state.pop(k, None)
                    st.rerun()

        st.divider()

        if st.button("🚪 Logout App", use_container_width=True):
            from utils import data_store
            data_store.clear_all()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.switch_page("pages/0_Login.py")

        st.caption("Built with Angel One SmartAPI")

    return market_open()
