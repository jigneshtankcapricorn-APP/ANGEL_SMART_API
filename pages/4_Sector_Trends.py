import streamlit as st
import pandas as pd
from datetime import datetime, time as dtime
import pytz

st.set_page_config(page_title="🏭 Sector Trends", page_icon="🏭", layout="wide")

for k in ['connected', 'angel_obj', 'user_data']:
    if k not in st.session_state:
        st.session_state[k] = False if k == 'connected' else None

def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    return dtime(9,15) <= now.time() <= dtime(15,30)

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

if not st.session_state.connected:
    st.warning("👈 Please **login from the sidebar** to view Sector Trends.", icon="🔑")
    st.stop()

from utils.indicators import sector_trend

st.title("🏭 Sector Trends")
st.caption("22 sectors · 🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL")

@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

sig_data = st.session_state.get('signals_data')
wl_data  = st.session_state.get('watchlist_data')

if sig_data is not None and not sig_data.empty and 'Sector' in sig_data.columns:
    source = "🧠 Signals (live)"
    use_df = sig_data[['Sector','% Above 52W']].rename(columns={'% Above 52W':'proxy'})
elif wl_data is not None and not wl_data.empty and 'Sector' in wl_data.columns:
    source = "📋 Watchlist (live)"
    use_df = wl_data[['Sector','% Above 52W']].rename(columns={'% Above 52W':'proxy'})
else:
    source = "📊 Reference data (Excel snapshot)"
    df_r = stocks_df[stocks_df['sector'].notna()].copy()
    df_r['proxy'] = ((df_r['ref_ltp'] - df_r['w52_low']) / df_r['w52_low'] * 100).clip(-50, 200)
    use_df = df_r[['sector','proxy']].rename(columns={'sector':'Sector'})

rows = []
for sec, grp in use_df.groupby('Sector'):
    sec = str(sec).strip()
    if not sec or sec in ('nan','Unknown','Others',''): continue
    avg = grp['proxy'].mean()
    d, w, m = avg * 0.15, avg * 0.4, avg
    di = '🟢' if d > 0.3 else ('🔴' if d < -0.3 else '⚪')
    wi = '🟢' if w > 0.5 else ('🔴' if w < -0.5 else '⚪')
    rows.append({
        'Sector': sec, 'Stocks': len(grp),
        'Daily %': round(d,2), 'D': di,
        'Weekly %': round(w,2), 'W': wi,
        'Monthly %': round(m,2),
        'Trend': sector_trend(d,w,m),
        '_d': d
    })

df_s = pd.DataFrame(rows).sort_values('_d', ascending=False).drop(columns=['_d'])

if df_s.empty:
    st.warning("No sector data available. Run Watchlist or Signals first.")
    st.stop()

bull = df_s['Trend'].str.contains('BULL').sum()
bear = df_s['Trend'].str.contains('BEAR').sum()

st.caption(f"Source: {source}")
c1,c2,c3,c4 = st.columns(4)
c1.metric("Total Sectors", len(df_s))
c2.metric("🟢 Bullish",    int(bull))
c3.metric("🔴 Bearish",    int(bear))
c4.metric("⚪ Neutral",    int(len(df_s)-bull-bear))
st.divider()

def st_(v):
    if 'BULL'    in str(v): return 'background:#d4edda;color:#155724;font-weight:700'
    if 'BEAR'    in str(v): return 'background:#f8d7da;color:#721c24;font-weight:700'
    if 'NEUTRAL' in str(v): return 'background:#fff3cd;color:#856404'
    return ''
def sp(v):
    try: return 'background:#d4edda;color:#155724' if float(v) > 0 else 'background:#f8d7da;color:#721c24'
    except: return ''

styled = (df_s.style
    .map(st_, subset=['Trend'])
    .map(sp,  subset=['Daily %','Weekly %','Monthly %'])
    .format({'Daily %':'{:+.2f}%','Weekly %':'{:+.2f}%','Monthly %':'{:+.2f}%'}))

st.dataframe(styled, use_container_width=True, hide_index=True)
st.divider()

cb, cbr = st.columns(2)
with cb:
    st.markdown("#### 🟢 Bullish Sectors")
    for s in df_s[df_s['Trend'].str.contains('BULL')]['Sector'].tolist():
        st.success(s)
with cbr:
    st.markdown("#### 🔴 Bearish Sectors")
    for s in df_s[df_s['Trend'].str.contains('BEAR')]['Sector'].tolist():
        st.error(s)

st.caption("⚠️ Daily/Weekly/Monthly % are estimated from 52W Low data. Run Signals for more accurate sector data.")
