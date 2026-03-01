"""
pages/1_Dashboard.py — Market Dashboard
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import pytz

from utils.login import render_sidebar, is_market_open
from utils.angel_connect import fetch_index_history, fetch_index_data
from utils.indicators import sector_trend

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

connected = render_sidebar()
if not connected:
    from utils.login import require_login
    require_login()

obj = st.session_state.angel_obj

def pct_change(new, old):
    if old and old != 0:
        return round((new - old) / old * 100, 2)
    return 0.0

st.markdown("## 📊 Market Dashboard")
mkt = "🟢 MARKET OPEN" if is_market_open() else "🔴 MARKET CLOSED"
ist = pytz.timezone('Asia/Kolkata')
st.markdown(f"**{mkt}** &nbsp;|&nbsp; {datetime.now(ist).strftime('%d %b %Y %H:%M IST')}")

if st.button("🔄 Refresh Dashboard", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

INDICES = ['Nifty 50', 'Bank Nifty', 'Nifty 500']
index_rows = []

with st.spinner("Fetching index data from Angel One…"):
    for idx_name in INDICES:
        try:
            history = fetch_index_history(obj, idx_name, days=45)
            live    = fetch_index_data(obj, idx_name)
            ltp = live.get('ltp', 0) if live else 0
            if not ltp and history:
                ltp = history[-1]['close']

            daily_pct = pct_change(ltp, history[-2]['close']) if history and len(history) >= 2 else 0
            weekly_pct = pct_change(ltp, history[-6]['close']) if history and len(history) >= 6 else 0
            monthly_pct = pct_change(ltp, history[-22]['close']) if history and len(history) >= 22 else 0

            trend = sector_trend(daily_pct, weekly_pct, monthly_pct)
            index_rows.append({'Index': idx_name, 'LTP': ltp,
                'Daily %': daily_pct, 'Weekly %': weekly_pct,
                'Monthly %': monthly_pct, 'Trend': trend})
        except Exception:
            index_rows.append({'Index': idx_name, 'LTP': 0,
                'Daily %': 0, 'Weekly %': 0, 'Monthly %': 0, 'Trend': '⚠️ ERROR'})

for row in index_rows:
    c_name, c_ltp, c_d, c_w, c_m, c_trend = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5])
    with c_name:  st.markdown(f"### {row['Index']}")
    with c_ltp:   st.metric("LTP",      f"₹ {row['LTP']:,.2f}")
    with c_d:     st.metric("Daily %",  f"{row['Daily %']:+.2f}%",  delta=f"{row['Daily %']:+.2f}%")
    with c_w:     st.metric("Weekly %", f"{row['Weekly %']:+.2f}%", delta=f"{row['Weekly %']:+.2f}%")
    with c_m:     st.metric("Monthly %",f"{row['Monthly %']:+.2f}%",delta=f"{row['Monthly %']:+.2f}%")
    with c_trend:
        t = row['Trend']
        if 'BULL' in t:   st.success(t)
        elif 'BEAR' in t: st.error(t)
        else:             st.info(t)
    st.divider()

st.markdown("### 📋 Summary Table")
df = pd.DataFrame(index_rows)
if not df.empty:
    df_d = df.copy()
    df_d['LTP']       = df_d['LTP'].apply(lambda x: f"₹ {x:,.2f}")
    df_d['Daily %']   = df_d['Daily %'].apply(lambda x: f"{x:+.2f}%")
    df_d['Weekly %']  = df_d['Weekly %'].apply(lambda x: f"{x:+.2f}%")
    df_d['Monthly %'] = df_d['Monthly %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df_d, use_container_width=True, hide_index=True)

st.caption("Daily: today vs prev close · Weekly: vs 5 days ago · Monthly: vs 22 days ago")
