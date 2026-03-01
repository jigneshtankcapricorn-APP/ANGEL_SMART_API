import streamlit as st
from datetime import datetime, time as dtime
import pytz

st.set_page_config(
    page_title="Angel One Trading",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── session init ───────────────────────────────────────────────────
for k in ['connected', 'angel_obj', 'user_data']:
    if k not in st.session_state:
        st.session_state[k] = False if k == 'connected' else None

# ── market open check ──────────────────────────────────────────────
def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

# ── sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Angel One")
    ist = pytz.timezone('Asia/Kolkata')
    st.caption(datetime.now(ist).strftime('%d %b %Y %H:%M IST'))
    st.divider()

    if market_open():
        st.success("🟢 MARKET OPEN")
    else:
        st.error("🔴 MARKET CLOSED")

    st.divider()

    if not st.session_state.connected:
        st.subheader("🔑 Login")
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
            for k in ['connected', 'angel_obj', 'user_data', 'watchlist_data', 'signals_data']:
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()
    st.caption("Built with Angel One SmartAPI")

# ── main content ───────────────────────────────────────────────────
st.markdown("""
<style>
.banner {
    background: linear-gradient(135deg,#1A73E8,#0D47A1);
    color:white; padding:28px; border-radius:12px;
    text-align:center; margin-bottom:20px;
}
.banner h1 { margin:0; font-size:1.9rem; }
.banner p  { margin:4px 0 0; opacity:.85; }
.card {
    background:#f8f9fa; border-radius:10px;
    padding:18px; border-left:4px solid #1A73E8;
}
.card h3 { margin:0 0 6px; font-size:1rem; }
.card p  { margin:0; font-size:.85rem; color:#555; }
</style>
<div class="banner">
  <h1>🚀 Angel One Trading Dashboard</h1>
  <p>SuperTrend · Watchlist · Signals · Sector Analysis</p>
</div>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="card"><h3>📊 Dashboard</h3><p>Nifty 50, Bank Nifty, Nifty 500<br>Daily / Weekly / Monthly %<br>Market status</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="card"><h3>📋 Watchlist</h3><p>Filter by % above 52W Low<br>Market Cap filter<br>🔥 Volume breakouts</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="card"><h3>🧠 Signals</h3><p>SuperTrend (10,3)<br>EMA 23 · Swing High<br>🟢 BUY · ⚪ WATCH</p></div>', unsafe_allow_html=True)
with c4:
    st.markdown('<div class="card"><h3>🏭 Sector Trends</h3><p>22 sectors ranked<br>Bull / Bear / Neutral<br>Avg Daily %</p></div>', unsafe_allow_html=True)

st.markdown("---")

if not st.session_state.connected:
    st.info("👈 **Login from the sidebar** then use the pages in the top-left menu to navigate.", icon="🔑")
else:
    st.success("✅ Connected! Click any page in the **top-left sidebar menu** to navigate.", icon="🚀")
    c1, c2, c3 = st.columns(3)
    wl  = st.session_state.get('watchlist_data')
    sig = st.session_state.get('signals_data')
    c1.metric("Stocks in DB", "500")
    c2.metric("Watchlist",    len(wl)  if wl  is not None else "—")
    c3.metric("Signals",      len(sig) if sig is not None else "—")
