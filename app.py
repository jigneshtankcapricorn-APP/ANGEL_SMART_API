"""
app.py — Angel One Trading Dashboard
Main entry point: handles login, sidebar, and home screen.
"""
import streamlit as st
from datetime import datetime
import pytz

from utils.angel_connect import connect_angel_one

# ──────────────────────────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Angel One Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────
# Global CSS
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main-banner {
    background: linear-gradient(135deg, #1A73E8 0%, #0D47A1 100%);
    color: white;
    padding: 24px 32px;
    border-radius: 14px;
    margin-bottom: 24px;
    text-align: center;
  }
  .main-banner h1 { margin: 0; font-size: 2rem; }
  .main-banner p  { margin: 6px 0 0; opacity: .85; font-size: 1rem; }
  .feat-card {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 20px;
    border-left: 5px solid #1A73E8;
    height: 100%;
  }
  .feat-card h3 { margin: 0 0 8px; }
  .feat-card p  { margin: 0; font-size: .9rem; color: #555; }
  section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
  }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def is_market_open() -> bool:
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    t = now.time()
    from datetime import time as dt_time
    return dt_time(9, 15) <= t <= dt_time(15, 30)


def format_dt() -> str:
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%d %b %Y  %H:%M IST')


# ──────────────────────────────────────────────────────────────────
# Session-State Initialisation
# ──────────────────────────────────────────────────────────────────
for key in ['connected', 'angel_obj', 'user_data']:
    if key not in st.session_state:
        st.session_state[key] = False if key == 'connected' else None


# ──────────────────────────────────────────────────────────────────
# Sidebar — Login Panel
# ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Angel One Trading")
    st.caption(format_dt())
    st.markdown("---")

    mkt_open = is_market_open()
    st.markdown(
        f"{'🟢 **MARKET OPEN**' if mkt_open else '🔴 **MARKET CLOSED**'}"
    )
    st.markdown("---")

    if not st.session_state.connected:
        st.markdown("### 🔑 Login")
        if st.button("🔴 CONNECT TO ANGEL ONE", use_container_width=True,
                     type="primary"):
            with st.spinner("Connecting to Angel One…"):
                obj, user = connect_angel_one()
                if obj:
                    st.session_state.angel_obj  = obj
                    st.session_state.user_data  = user
                    st.session_state.connected  = True
                    st.rerun()
    else:
        user = st.session_state.user_data or {}
        name = (user.get('name') or user.get('clientName') or
                user.get('client_name') or 'Connected')
        st.success(f"✅ {name}")
        if st.button("🔌 Disconnect", use_container_width=True):
            for k in ['connected', 'angel_obj', 'user_data',
                      'watchlist_data', 'signals_data']:
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")
    st.markdown("**🗂 Navigation**")
    # ✅ FIXED: plain filenames — no emoji in path
    st.page_link("pages/1_Dashboard.py",      label="📊  Dashboard")
    st.page_link("pages/2_Watchlist.py",      label="📋  Watchlist")
    st.page_link("pages/3_Signals.py",        label="🧠  Signals")
    st.page_link("pages/4_Sector_Trends.py",  label="🏭  Sector Trends")

    st.markdown("---")
    st.caption("Built with Angel One SmartAPI + Streamlit")


# ──────────────────────────────────────────────────────────────────
# Home Page Content
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-banner">
  <h1>🚀 Angel One Trading Dashboard</h1>
  <p>SuperTrend • Watchlist • Signals • Sector Analysis</p>
</div>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("""<div class="feat-card">
      <h3>📊 Dashboard</h3>
      <p>Nifty 50 · Nifty 500 · Bank Nifty<br>
         Daily / Weekly / Monthly %<br>
         Market open / close status</p>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown("""<div class="feat-card">
      <h3>📋 Watchlist</h3>
      <p>Filter by % above 52W Low<br>
         Min Market Cap slider<br>
         🔥 Volume ratio highlight</p>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown("""<div class="feat-card">
      <h3>🧠 Signals</h3>
      <p>SuperTrend (10, 3)<br>
         ATR · 23-EMA · Swing High<br>
         🟢 BUY / ⚪ WATCH · Risk %</p>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown("""<div class="feat-card">
      <h3>🏭 Sector Trends</h3>
      <p>22 sectors ranked<br>
         Avg Daily / Weekly / Monthly %<br>
         🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL</p>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

if not st.session_state.connected:
    st.warning(
        "👈 **Connect to Angel One** using the sidebar button to unlock all pages.",
        icon="🔑"
    )
else:
    st.success("✅ Connected! Use the sidebar links to navigate.", icon="🚀")
    st.markdown("### Quick Stats")
    qs1, qs2, qs3 = st.columns(3)
    wl  = st.session_state.get('watchlist_data')
    sig = st.session_state.get('signals_data')
    qs1.metric("Stocks in DB", "500")
    qs2.metric("Watchlist",    len(wl)  if wl  is not None else "—")
    qs3.metric("Signals",      len(sig) if sig is not None else "—")
