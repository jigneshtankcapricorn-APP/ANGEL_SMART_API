"""
pages/2_Watchlist.py — Watchlist with live Angel One data
"""
import streamlit as st
import pandas as pd
import time

from utils.login import render_sidebar, require_login
from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import compute_vol_ratio

st.set_page_config(page_title="Watchlist", page_icon="📋", layout="wide")

connected = render_sidebar()
if not connected:
    require_login()

obj = st.session_state.angel_obj

@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

# ── Sidebar Filters ───────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Watchlist Filters")
min_pct  = st.sidebar.number_input("Min % Above 52W Low", 0.0, 100.0, 10.0, 0.5)
max_pct  = st.sidebar.number_input("Max % Above 52W Low", 0.0, 100.0, 15.0, 0.5)
min_mcap = st.sidebar.number_input("Min Market Cap (Cr)", 500.0, value=500.0, step=100.0)
if min_mcap < 500: min_mcap = 500.0

# ── Header ────────────────────────────────────────────────────────
st.markdown("## 📋 Watchlist")
st.caption(f"Filter: {min_pct}–{max_pct}% above 52W Low · Min ₹{min_mcap:,.0f} Cr Market Cap")
run_btn = st.button("🔄 FETCH / REFRESH WATCHLIST", type="primary", use_container_width=True)

def pre_filter(df, lo, hi, mcap):
    d = df[(df['ref_ltp'] > 0) & (df['w52_low'] > 0) & (df['market_cap_cr'] >= mcap)].copy()
    d['ref_pct'] = ((d['ref_ltp'] - d['w52_low']) / d['w52_low']) * 100
    return d[(d['ref_pct'] >= lo) & (d['ref_pct'] <= hi)].reset_index(drop=True)

def status_label(pct):
    if pct <= 12: return '🟢 STRONG'
    if pct <= 15: return '🟡 MODERATE'
    return '🟠 WATCH'

if run_btn or 'watchlist_data' in st.session_state:
    if run_btn:
        st.session_state.pop('watchlist_data', None)

    if 'watchlist_data' not in st.session_state:
        candidates = pre_filter(stocks_df, min_pct, max_pct, min_mcap)
        if candidates.empty:
            st.warning("No candidates found with current filters.")
            st.stop()

        st.info(f"📊 {len(candidates)} candidates found. Fetching live prices…")
        instruments = load_instrument_master()
        results = []
        prog  = st.progress(0)
        label = st.empty()

        for i, (_, row) in enumerate(candidates.iterrows()):
            sym = row['symbol']
            label.text(f"Fetching {row['name']} ({i+1}/{len(candidates)})…")
            prog.progress((i + 1) / len(candidates))

            token = get_token(instruments, sym)
            if not token: continue

            trading_sym = sym.replace('NSE:', '')
            ltp = fetch_ltp(obj, 'NSE', trading_sym, token) or row['ref_ltp']

            history = fetch_historical_ohlc(obj, token, 'NSE', days=30)
            if history:
                volume      = history[-1]['volume']
                avg_vol_20d = sum(h['volume'] for h in history[-21:-1]) / 20 if len(history) >= 21 else row['ref_avg_vol_20d']
            else:
                volume      = row['ref_volume']
                avg_vol_20d = row['ref_avg_vol_20d']

            w52_low   = row['w52_low']
            pct_above = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0
            vol_ratio, vol_label = compute_vol_ratio(volume, avg_vol_20d)

            results.append({
                'Name': row['name'], 'Symbol': trading_sym, 'Sector': row['sector'],
                'LTP': round(ltp, 2), '52W Low': round(w52_low, 2),
                '% Above 52W Low': round(pct_above, 2),
                'Market Cap (Cr)': round(row['market_cap_cr'], 0),
                'Volume': int(volume), 'Avg Vol 20D': int(avg_vol_20d),
                'Vol Ratio': vol_label, '_vr': vol_ratio,
                'Status': status_label(pct_above),
            })
            time.sleep(0.15)

        prog.empty(); label.empty()
        df_r = pd.DataFrame(results)
        if not df_r.empty:
            df_r = df_r[
                (df_r['% Above 52W Low'] >= min_pct) &
                (df_r['% Above 52W Low'] <= max_pct) &
                (df_r['Market Cap (Cr)']  >= min_mcap)
            ].sort_values('% Above 52W Low').reset_index(drop=True)
        st.session_state.watchlist_data = df_r

    df_r = st.session_state.watchlist_data
    if df_r.empty:
        st.warning("No stocks matched filters after live check.")
        st.stop()

    strong = (df_r['Status']=='🟢 STRONG').sum()
    mod    = (df_r['Status']=='🟡 MODERATE').sum()
    watch  = (df_r['Status']=='🟠 WATCH').sum()
    vb     = (df_r['_vr'] >= 1.5).sum()

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Total", len(df_r)); m2.metric("🟢 STRONG", strong)
    m3.metric("🟡 MODERATE", mod); m4.metric("🟠 WATCH", watch); m5.metric("🔥 Vol Breakout", vb)

    vb_stocks = df_r[df_r['_vr'] >= 1.5]
    if not vb_stocks.empty:
        st.error("🔥 **VOLUME BREAKOUT:** " + ", ".join(f"{r['Symbol']} ({r['Vol Ratio']})" for _, r in vb_stocks.iterrows()))

    st.markdown("---")

    def cs(v):
        if 'STRONG'   in str(v): return 'background-color:#d4edda;color:#155724;font-weight:700'
        if 'MODERATE' in str(v): return 'background-color:#fff3cd;color:#856404;font-weight:700'
        if 'WATCH'    in str(v): return 'background-color:#f8d7da;color:#721c24'
        return ''
    def cv(v):
        if '🔥' in str(v): return 'background-color:#d4edda;color:#155724;font-weight:700'
        if '⚡' in str(v): return 'background-color:#fff3cd;color:#856404'
        return ''

    show_cols = ['Name','Symbol','Sector','LTP','52W Low','% Above 52W Low','Market Cap (Cr)','Volume','Avg Vol 20D','Vol Ratio','Status']
    styled = (df_r[show_cols].style
        .map(cs, subset=['Status'])
        .map(cv, subset=['Vol Ratio'])
        .format({'LTP':'₹{:,.2f}','52W Low':'₹{:,.2f}','% Above 52W Low':'{:.2f}%',
                 'Market Cap (Cr)':'{:,.0f}','Volume':'{:,}','Avg Vol 20D':'{:,}'}))
    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.info("⚙️ Set filters in the sidebar then click **🔄 FETCH / REFRESH WATCHLIST**")
