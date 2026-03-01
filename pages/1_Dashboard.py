"""
pages/1_📊_Dashboard.py
Market Dashboard: Nifty 50, Nifty 500, Bank Nifty
Daily / Weekly / Monthly % with Trend status.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import pytz

from utils.angel_connect import fetch_index_history, fetch_index_data
from utils.indicators import sector_trend

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

# ──────────────────────────────────────────────────────────────────
def require_login():
    if not st.session_state.get('connected'):
        st.warning("👈 Please **Connect to Angel One** from the Home page first.")
        st.stop()

require_login()
obj = st.session_state.angel_obj


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def pct_change(new, old):
    if old and old != 0:
        return round((new - old) / old * 100, 2)
    return 0.0


def trend_label(daily, weekly, monthly):
    t = sector_trend(daily, weekly, monthly)
    return t


def pct_icon(val, thresholds=(0.3, 0.5)):
    lo, hi = thresholds
    if val > hi:   return f"🟢 +{val:.2f}%"
    if val < -hi:  return f"🔴 {val:.2f}%"
    return f"⚪ {val:.2f}%"


def is_market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    from datetime import time as dt_time
    return dt_time(9, 15) <= now.time() <= dt_time(15, 30)


# ──────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────
st.markdown("## 📊 Market Dashboard")
mkt = "🟢 MARKET OPEN" if is_market_open() else "🔴 MARKET CLOSED"
st.markdown(f"**{mkt}** &nbsp;|&nbsp; {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %b %Y %H:%M IST')}")

if st.button("🔄 Refresh Dashboard", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

# ──────────────────────────────────────────────────────────────────
# Fetch & Display Index Data
# ──────────────────────────────────────────────────────────────────
INDICES = ['Nifty 50', 'Bank Nifty', 'Nifty 500']
index_rows = []

with st.spinner("Fetching index data from Angel One…"):
    for idx_name in INDICES:
        try:
            history = fetch_index_history(obj, idx_name, days=45)
            live    = fetch_index_data(obj, idx_name)

            ltp = live.get('ltp', 0) if live else 0

            # If live LTP unavailable, use last close from history
            if not ltp and history:
                ltp = history[-1]['close']

            daily_pct   = 0.0
            weekly_pct  = 0.0
            monthly_pct = 0.0

            if history and len(history) >= 2:
                # Daily: today vs previous close
                daily_pct = pct_change(ltp, history[-2]['close'])

            if history and len(history) >= 6:
                # Weekly: today vs ~5 trading days ago
                weekly_pct = pct_change(ltp, history[-6]['close'])

            if history and len(history) >= 22:
                # Monthly: today vs ~22 trading days ago
                monthly_pct = pct_change(ltp, history[-22]['close'])

            trend = trend_label(daily_pct, weekly_pct, monthly_pct)
            index_rows.append({
                'Index':   idx_name,
                'LTP':     ltp,
                'Daily %':  daily_pct,
                'Weekly %': weekly_pct,
                'Monthly %':monthly_pct,
                'Trend':    trend,
            })
        except Exception as e:
            index_rows.append({
                'Index':   idx_name,
                'LTP':     0,
                'Daily %':  0,
                'Weekly %': 0,
                'Monthly %':0,
                'Trend':    '⚠️ ERROR',
            })

# ── Metric Cards ────────────────────────────────────────────────
for row in index_rows:
    c_name, c_ltp, c_d, c_w, c_m, c_trend = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5])
    with c_name:
        st.markdown(f"### {row['Index']}")
    with c_ltp:
        st.metric("LTP", f"₹ {row['LTP']:,.2f}")
    with c_d:
        d = row['Daily %']
        st.metric("Daily %", f"{d:+.2f}%", delta=f"{d:+.2f}%")
    with c_w:
        w = row['Weekly %']
        st.metric("Weekly %", f"{w:+.2f}%", delta=f"{w:+.2f}%")
    with c_m:
        m = row['Monthly %']
        st.metric("Monthly %", f"{m:+.2f}%", delta=f"{m:+.2f}%")
    with c_trend:
        trend = row['Trend']
        if 'BULL' in trend:
            st.success(trend)
        elif 'BEAR' in trend:
            st.error(trend)
        else:
            st.info(trend)
    st.divider()

# ── Summary Table ────────────────────────────────────────────────
st.markdown("### 📋 Summary Table")
df = pd.DataFrame(index_rows)
if not df.empty:
    df_disp = df.copy()
    df_disp['LTP']      = df_disp['LTP'].apply(lambda x: f"₹ {x:,.2f}")
    df_disp['Daily %']  = df_disp['Daily %'].apply(lambda x: f"{x:+.2f}%")
    df_disp['Weekly %'] = df_disp['Weekly %'].apply(lambda x: f"{x:+.2f}%")
    df_disp['Monthly %']= df_disp['Monthly %'].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(df_disp, use_container_width=True, hide_index=True)

# ── Legend ────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**Trend Logic:** 🟢 BULL = all timeframes positive | "
    "🔴 BEAR = all negative | ⚪ NEUTRAL = mixed signals  \n"
    "Daily: today vs prev close · Weekly: vs 5 days ago · Monthly: vs 22 days ago"
)
