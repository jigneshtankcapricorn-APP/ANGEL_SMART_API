import streamlit as st
from datetime import datetime, time as dtime
import pytz

st.set_page_config(
    page_title="Angel One Trading",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── App-level login guard ─────────────────────────────────────────
if not st.session_state.get("app_authenticated"):
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div style='text-align:center;padding:60px 0 20px'>
      <h1>🔐 Angel One Trading Dashboard</h1>
      <p style='color:#555;font-size:1.1rem'>Please login to continue</p>
    </div>
    """, unsafe_allow_html=True)
    col = st.columns([1,2,1])[1]
    with col:
        if st.button("Go to Login →", use_container_width=True, type="primary"):
            st.switch_page("pages/0_Login.py")
    st.stop()

# ── Init session ──────────────────────────────────────────────────
for k in ['connected', 'angel_obj', 'user_data']:
    if k not in st.session_state:
        st.session_state[k] = False if k == 'connected' else None

# ── Sidebar ───────────────────────────────────────────────────────
from utils.sidebar import render_sidebar
render_sidebar()

def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    return dtime(9,15) <= now.time() <= dtime(15,30)

# ── Main banner ───────────────────────────────────────────────────
st.markdown("""
<style>
.banner { background:linear-gradient(135deg,#1A73E8,#0D47A1); color:white;
          padding:28px; border-radius:12px; text-align:center; margin-bottom:20px; }
.banner h1 { margin:0; font-size:1.9rem; }
.banner p  { margin:4px 0 0; opacity:.85; }
.card { background:#f8f9fa; border-radius:10px; padding:18px; border-left:4px solid #1A73E8; }
.card h3 { margin:0 0 6px; font-size:1rem; }
.card p  { margin:0; font-size:.85rem; color:#555; }
</style>
<div class="banner">
  <h1>🚀 Angel One Trading Dashboard</h1>
  <p>SuperTrend · Watchlist · Signals · Sector Analysis</p>
</div>
""", unsafe_allow_html=True)

c1,c2,c3,c4 = st.columns(4)
with c1:
    st.markdown('<div class="card"><h3>📊 Dashboard</h3><p>Nifty 50, Bank Nifty, Nifty 500<br>Daily / Weekly / Monthly %</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="card"><h3>📋 Watchlist</h3><p>2,242 NSE stocks<br>Filter by % above 52W Low<br>🔥 Volume breakouts</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="card"><h3>🧠 Signals</h3><p>SuperTrend (10,3)<br>EMA 23 · Swing High<br>🟢 BUY · ⚪ WATCH</p></div>', unsafe_allow_html=True)
with c4:
    st.markdown('<div class="card"><h3>🏭 Sector Trends</h3><p>Live NSE Sector Indices<br>Real Daily / Weekly / Monthly %</p></div>', unsafe_allow_html=True)

st.markdown("---")

if not st.session_state.connected:
    st.info("👈 **Connect to Angel One** from the sidebar to start fetching live data.", icon="🔑")
else:
    st.success("✅ Connected! Navigate using the sidebar menu.", icon="🚀")
    from utils import data_store
    wl  = data_store.load("watchlist_df")
    sig = data_store.load("signals_df")
    sec = data_store.load("sector_df")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Universe",   "2,242 stocks")
    c2.metric("Watchlist",  len(wl)  if wl  is not None else "—")
    c3.metric("Signals",    len(sig) if sig is not None else "—")
    c4.metric("Sectors",    len(sec) if sec is not None else "—")
