import streamlit as st
from datetime import datetime
import pytz

st.set_page_config(page_title="📊 Dashboard", page_icon="📊", layout="wide")

from utils.sidebar import render_sidebar, require_app_login, market_open, check_session_alive
require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.angel_connect import fetch_index_history, fetch_index_data
from utils.indicators import sector_trend

st.title("📊 Market Dashboard")
ist = pytz.timezone('Asia/Kolkata')
st.caption(f"{'🟢 MARKET OPEN' if market_open() else '🔴 MARKET CLOSED'}  |  {datetime.now(ist).strftime('%d %b %Y %H:%M IST')}")

if st.button("🔄 Refresh", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.divider()

def pct(n, o):
    return round((n - o) / o * 100, 2) if o else 0.0

obj     = st.session_state.angel_obj
INDICES = ['Nifty 50', 'Bank Nifty', 'Nifty 500']
rows    = []

with st.spinner("Fetching live index data…"):
    for idx in INDICES:
        try:
            hist = fetch_index_history(obj, idx, days=45)
            live = fetch_index_data(obj, idx)
            ltp  = live.get('ltp', 0) if live else 0
            if not ltp and hist: ltp = hist[-1]['close']
            d = pct(ltp, hist[-2]['close'])  if len(hist) >= 2  else 0
            w = pct(ltp, hist[-6]['close'])  if len(hist) >= 6  else 0
            m = pct(ltp, hist[-22]['close']) if len(hist) >= 22 else 0
            rows.append({'Index': idx, 'LTP': ltp, 'Daily': d, 'Weekly': w, 'Monthly': m,
                         'Trend': sector_trend(d, w, m)})
        except Exception:
            rows.append({'Index': idx, 'LTP': 0, 'Daily': 0, 'Weekly': 0, 'Monthly': 0, 'Trend': '⚠️ ERR'})

for r in rows:
    ca,cb,cc,cd,ce,cf = st.columns([2,1.8,1.5,1.5,1.5,1.5])
    ca.markdown(f"### {r['Index']}")
    cb.metric("LTP",       f"₹{r['LTP']:,.2f}")
    cc.metric("Daily %",   f"{r['Daily']:+.2f}%",   delta=f"{r['Daily']:+.2f}%")
    cd.metric("Weekly %",  f"{r['Weekly']:+.2f}%",  delta=f"{r['Weekly']:+.2f}%")
    ce.metric("Monthly %", f"{r['Monthly']:+.2f}%", delta=f"{r['Monthly']:+.2f}%")
    t = r['Trend']
    if 'BULL' in t:   cf.success(t)
    elif 'BEAR' in t: cf.error(t)
    else:             cf.info(t)
    st.divider()

st.caption("Daily = vs prev close · Weekly = vs 5 days ago · Monthly = vs 22 days ago")
