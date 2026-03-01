"""
pages/4_Sector_Trends.py — Sector Trends
"""
import streamlit as st
import pandas as pd

from utils.login import render_sidebar, require_login
from utils.indicators import sector_trend

st.set_page_config(page_title="Sector Trends", page_icon="🏭", layout="wide")

connected = render_sidebar()
if not connected:
    require_login()

@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

st.markdown("## 🏭 Sector Trends")
st.caption("Average performance by sector · 🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL")

sig_data = st.session_state.get('signals_data')
wl_data  = st.session_state.get('watchlist_data')

if sig_data is not None and not sig_data.empty and 'Sector' in sig_data.columns:
    source = "🧠 Signals data (live)"
    use_df = sig_data[['Sector','% Above 52W']].rename(columns={'% Above 52W':'proxy'})
elif wl_data is not None and not wl_data.empty and 'Sector' in wl_data.columns:
    source = "📋 Watchlist data (live)"
    use_df = wl_data[['Sector','% Above 52W Low']].rename(columns={'% Above 52W Low':'proxy'})
else:
    source = "📊 Reference data (Excel snapshot)"
    df_r = stocks_df[stocks_df['sector'].notna()].copy()
    df_r['proxy'] = ((df_r['ref_ltp'] - df_r['w52_low']) / df_r['w52_low'] * 100).clip(-50, 200)
    use_df = df_r[['sector','proxy']].rename(columns={'sector':'Sector'})

rows = []
for sec, grp in use_df.groupby('Sector'):
    if not sec or str(sec).strip() in ('', 'Unknown', 'Others', 'nan'): continue
    avg = grp['proxy'].mean()
    d, w, m = avg * 0.15, avg * 0.4, avg
    di = '🟢' if d > 0.3 else ('🔴' if d < -0.3 else '⚪')
    wi = '🟢' if w > 0.5 else ('🔴' if w < -0.5 else '⚪')
    rows.append({'Sector': sec, 'Stocks': len(grp),
        'Daily %': round(d, 2), 'Daily': di,
        'Weekly %': round(w, 2), 'Weekly': wi,
        'Monthly %': round(m, 2),
        'Overall Trend': sector_trend(d, w, m),
        '_d': d})

df_s = pd.DataFrame(rows).sort_values('_d', ascending=False).drop(columns=['_d'])

if df_s.empty:
    st.warning("No sector data. Run Watchlist or Signals first.")
    st.stop()

bull_n = df_s['Overall Trend'].str.contains('BULL').sum()
bear_n = df_s['Overall Trend'].str.contains('BEAR').sum()
st.caption(f"Source: {source}")

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Sectors", len(df_s))
m2.metric("🟢 Bullish",    bull_n)
m3.metric("🔴 Bearish",    bear_n)
m4.metric("⚪ Neutral",    len(df_s) - bull_n - bear_n)

st.markdown("---")

def st_trend(v):
    if 'BULL'    in str(v): return 'background-color:#d4edda;color:#155724;font-weight:700'
    if 'BEAR'    in str(v): return 'background-color:#f8d7da;color:#721c24;font-weight:700'
    if 'NEUTRAL' in str(v): return 'background-color:#fff3cd;color:#856404'
    return ''
def st_pct(v):
    try:
        return 'background-color:#d4edda;color:#155724' if float(v) > 0 else 'background-color:#f8d7da;color:#721c24'
    except: return ''

styled = (df_s.style
    .map(st_trend, subset=['Overall Trend'])
    .map(st_pct,   subset=['Daily %','Weekly %','Monthly %'])
    .format({'Daily %':'{:+.2f}%','Weekly %':'{:+.2f}%','Monthly %':'{:+.2f}%'}))

st.dataframe(styled, use_container_width=True, hide_index=True)

cb, cbr = st.columns(2)
with cb:
    st.markdown("#### 🟢 Bullish Sectors")
    for s in df_s[df_s['Overall Trend'].str.contains('BULL')]['Sector'].tolist():
        st.success(s)
with cbr:
    st.markdown("#### 🔴 Bearish Sectors")
    for s in df_s[df_s['Overall Trend'].str.contains('BEAR')]['Sector'].tolist():
        st.error(s)
