import streamlit as st
from datetime import datetime, time as dtime
import pytz

st.set_page_config(page_title="📊 Dashboard", page_icon="📊", layout="wide")

# ── session guard ──────────────────────────────────────────────────
for k in ['connected', 'angel_obj', 'user_data']:
    if k not in st.session_state:
        st.session_state[k] = False if k == 'connected' else None

def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    return dtime(9,15) <= now.time() <= dtime(15,30)

# ── sidebar (login on every page) ─────────────────────────────────
with st.sidebar:
    st.title("📊 Angel One")
    ist = pytz.timezone('Asia/Kolkata')
    st.caption(datetime.now(ist).strftime('%d %b %Y %H:%M IST'))
    st.divider()
    if market_open(): st.success("🟢 MARKET OPEN")
    else:             st.error("🔴 MARKET CLOSED")
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
        name = u.get('name') or u.get('clientName') or 'Trader'
        st.success(f"✅ {name}")
        if st.button("🔌 Disconnect", use_container_width=True):
            for k in ['connected','angel_obj','user_data','watchlist_data','signals_data']:
                st.session_state.pop(k, None)
            st.rerun()
    st.divider()
    st.caption("Built with Angel One SmartAPI")

# ── page guard ─────────────────────────────────────────────────────
if not st.session_state.connected:
    st.warning("👈 Please **login from the sidebar** to view Dashboard.", icon="🔑")
    st.stop()

# ── page content ───────────────────────────────────────────────────
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

obj = st.session_state.angel_obj
INDICES = ['Nifty 50', 'Bank Nifty', 'Nifty 500']
rows = []

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
        except Exception as e:
            rows.append({'Index': idx, 'LTP': 0, 'Daily': 0, 'Weekly': 0, 'Monthly': 0, 'Trend': '⚠️ ERR'})

for r in rows:
    ca, cb, cc, cd, ce, cf = st.columns([2, 1.8, 1.5, 1.5, 1.5, 1.5])
    ca.markdown(f"### {r['Index']}")
    cb.metric("LTP",      f"₹{r['LTP']:,.2f}")
    cc.metric("Daily %",  f"{r['Daily']:+.2f}%",   delta=f"{r['Daily']:+.2f}%")
    cd.metric("Weekly %", f"{r['Weekly']:+.2f}%",  delta=f"{r['Weekly']:+.2f}%")
    ce.metric("Monthly %",f"{r['Monthly']:+.2f}%", delta=f"{r['Monthly']:+.2f}%")
    t = r['Trend']
    if 'BULL' in t:   cf.success(t)
    elif 'BEAR' in t: cf.error(t)
    else:             cf.info(t)
    st.divider()

st.caption("Daily = vs prev close · Weekly = vs 5 days ago · Monthly = vs 22 days ago")
