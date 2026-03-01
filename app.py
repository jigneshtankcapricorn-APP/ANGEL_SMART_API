"""
app.py — Home page
"""
import streamlit as st
from utils.login import render_sidebar

st.set_page_config(
    page_title="Angel One Trading",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .main-banner {
    background: linear-gradient(135deg, #1A73E8 0%, #0D47A1 100%);
    color: white; padding: 28px 32px; border-radius: 14px;
    margin-bottom: 24px; text-align: center;
  }
  .main-banner h1 { margin: 0; font-size: 2rem; }
  .main-banner p  { margin: 6px 0 0; opacity: .85; }
  .feat-card {
    background: #f8f9fa; border-radius: 12px; padding: 20px;
    border-left: 5px solid #1A73E8; height: 100%;
  }
  .feat-card h3 { margin: 0 0 8px; }
  .feat-card p  { margin: 0; font-size: .9rem; color: #555; }
</style>
""", unsafe_allow_html=True)

connected = render_sidebar()

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
      <p>Nifty 50 · Nifty 500 · Bank Nifty<br>Daily / Weekly / Monthly %<br>Market open / close status</p>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown("""<div class="feat-card">
      <h3>📋 Watchlist</h3>
      <p>Filter by % above 52W Low<br>Min Market Cap slider<br>🔥 Volume ratio highlight</p>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown("""<div class="feat-card">
      <h3>🧠 Signals</h3>
      <p>SuperTrend (10, 3)<br>ATR · 23-EMA · Swing High<br>🟢 BUY / ⚪ WATCH · Risk %</p>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown("""<div class="feat-card">
      <h3>🏭 Sector Trends</h3>
      <p>22 sectors ranked<br>Avg Daily / Weekly / Monthly %<br>🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL</p>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

if not connected:
    st.info("👈 **Login using the sidebar** to connect to Angel One and start trading analysis.", icon="🔑")
else:
    st.success("✅ Connected! Use the **sidebar** to navigate between pages.", icon="🚀")
    st.markdown("### Quick Stats")
    qs1, qs2, qs3 = st.columns(3)
    wl  = st.session_state.get('watchlist_data')
    sig = st.session_state.get('signals_data')
    qs1.metric("Stocks in DB", "500")
    qs2.metric("Watchlist",    len(wl)  if wl  is not None else "—")
    qs3.metric("Signals",      len(sig) if sig is not None else "—")
