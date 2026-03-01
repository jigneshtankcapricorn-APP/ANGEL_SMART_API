"""
pages/3_Signals.py — SuperTrend Signals
"""
import streamlit as st
import pandas as pd
import time

from utils.login import render_sidebar, require_login
from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import calculate_supertrend_signals, compute_risk, compute_vol_ratio

st.set_page_config(page_title="Signals", page_icon="🧠", layout="wide")

connected = render_sidebar()
if not connected:
    require_login()

obj = st.session_state.angel_obj

@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Signal Settings")
use_watchlist = st.sidebar.checkbox("Use Watchlist stocks only", value=True)

st.markdown("## 🧠 SuperTrend Signals")
st.caption("SuperTrend (10,3) · ATR(10) · EMA(23) · Swing High · BUY / WATCH")
run_btn = st.button("🔄 RUN SIGNAL ANALYSIS", type="primary", use_container_width=True)

def get_stocks():
    wl = st.session_state.get('watchlist_data')
    if use_watchlist and wl is not None and not wl.empty:
        rows = []
        for _, r in wl.iterrows():
            rows.append({'name': r['Name'], 'symbol': f"NSE:{r['Symbol']}",
                'sector': r['Sector'], 'ref_ltp': r['LTP'],
                'w52_low': r['52W Low'], 'market_cap_cr': r['Market Cap (Cr)'],
                'ref_volume': r['Volume'], 'ref_avg_vol_20d': r['Avg Vol 20D']})
        return pd.DataFrame(rows)
    return stocks_df.copy()

if run_btn or 'signals_data' in st.session_state:
    if run_btn:
        st.session_state.pop('signals_data', None)

    if 'signals_data' not in st.session_state:
        analysis_stocks = get_stocks()
        if analysis_stocks.empty:
            st.warning("Build Watchlist first or uncheck 'Use Watchlist stocks only'.")
            st.stop()

        instruments = load_instrument_master()
        src = "Watchlist" if use_watchlist and st.session_state.get('watchlist_data') is not None else "All 500 stocks"
        st.info(f"📊 Analysing **{len(analysis_stocks)} stocks** from {src}…")

        results, buy_list, watch_list, high_vol = [], [], [], []
        prog  = st.progress(0)
        label = st.empty()

        for i, (_, row) in enumerate(analysis_stocks.iterrows()):
            sym  = row['symbol']
            label.text(f"Analysing {row['name']} ({i+1}/{len(analysis_stocks)})…")
            prog.progress((i + 1) / len(analysis_stocks))

            token = get_token(instruments, sym)
            if not token: continue

            trading_sym = sym.replace('NSE:', '')
            ltp  = fetch_ltp(obj, 'NSE', trading_sym, token) or row['ref_ltp']
            ohlc = fetch_historical_ohlc(obj, token, 'NSE', days=40)

            if not ohlc or len(ohlc) < 15:
                time.sleep(0.1); continue

            ohlc[-1]['close'] = ltp
            sig = calculate_supertrend_signals(ohlc, period=10, multiplier=3)

            if sig['supertrend_status'] != '🟢 GREEN':
                time.sleep(0.1); continue

            volume      = ohlc[-1]['volume']
            avg_vol_20d = sum(c['volume'] for c in ohlc[-21:-1]) / 20 if len(ohlc) >= 21 else row['ref_avg_vol_20d']
            vol_ratio, vol_label = compute_vol_ratio(volume, avg_vol_20d)
            if vol_ratio >= 1.5:
                high_vol.append(f"{trading_sym} ({vol_ratio:.1f}x)")

            risk   = compute_risk(ltp, sig['ema23'])
            signal = '🟢 BUY' if sig['is_breakout'] else '⚪ WATCH'
            (buy_list if signal == '🟢 BUY' else watch_list).append(trading_sym)

            w52_low   = row['w52_low']
            pct_above = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0

            results.append({
                'Symbol': trading_sym, 'Sector': row['sector'],
                'LTP': round(ltp, 2), '52W Low': round(w52_low, 2),
                '% Above 52W': round(pct_above, 2),
                'Days Green': sig['days_green'],
                'Flat Zone?': '✅ YES' if sig['is_flat'] else '❌ NO',
                'Swing High': sig['swing_high'] or 'N/A',
                'Swing High Date': sig['swing_high_date'] or 'N/A',
                'Breakout?': '✅ YES' if sig['is_breakout'] else '❌ NO',
                '23-EMA': sig['ema23'] or 'N/A',
                'SL (5%)': risk['sl_5pct'],
                'Recommended SL': risk['recommended_sl'],
                'Risk % (EMA)': risk['risk_ema_pct'],
                'Volume': int(volume), 'Avg Vol 20D': int(avg_vol_20d),
                'Vol Ratio': vol_label, '_vr': vol_ratio,
                '_risk': risk['risk_ema_pct'],
                'Risk Status': risk['risk_status'],
                'SIGNAL': signal,
            })
            time.sleep(0.15)

        prog.empty(); label.empty()
        st.session_state.signals_data = pd.DataFrame(results) if results else pd.DataFrame()
        st.session_state.signals_meta = {
            'buy': buy_list, 'watch': watch_list,
            'high_vol': high_vol, 'total': len(analysis_stocks)
        }

    df_sig = st.session_state.signals_data
    meta   = st.session_state.get('signals_meta', {})

    if df_sig is None or df_sig.empty:
        st.warning("No GREEN SuperTrend stocks found.")
        st.stop()

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Analysed",    meta.get('total','—'))
    m2.metric("🟢 GREEN",    len(df_sig))
    m3.metric("🟢 BUY",      len(meta.get('buy',[])))
    m4.metric("⚪ WATCH",    len(meta.get('watch',[])))
    m5.metric("🔥 High Vol", len(meta.get('high_vol',[])))

    if meta.get('buy'):
        st.success("🟢 **BUY SIGNALS:** " + ", ".join(meta['buy']))
    if meta.get('high_vol'):
        st.error("🔥 **HIGH VOLUME:** " + ", ".join(meta['high_vol']))

    st.markdown("---")

    f1, f2 = st.columns(2)
    with f1:
        fs = st.multiselect("Signal", ['🟢 BUY','⚪ WATCH'], ['🟢 BUY','⚪ WATCH'])
    with f2:
        fr = st.multiselect("Risk", ['🟢 LOW RISK','🟡 MODERATE','⚠️ HIGH RISK'],
                            ['🟢 LOW RISK','🟡 MODERATE','⚠️ HIGH RISK'])

    df_show = df_sig[df_sig['SIGNAL'].isin(fs) & df_sig['Risk Status'].isin(fr)].copy()

    show_cols = ['Symbol','Sector','LTP','% Above 52W','Days Green','Flat Zone?',
                 'Swing High','Swing High Date','Breakout?','23-EMA',
                 'SL (5%)','Recommended SL','Risk % (EMA)',
                 'Volume','Avg Vol 20D','Vol Ratio','Risk Status','SIGNAL']

    def ss(v):
        if v=='🟢 BUY':  return 'background-color:#28a745;color:white;font-weight:700'
        if v=='⚪ WATCH': return 'background-color:#ffc107;color:black;font-weight:700'
        return ''
    def sr(v):
        if 'LOW'      in str(v): return 'background-color:#d4edda;color:#155724'
        if 'MODERATE' in str(v): return 'background-color:#fff3cd;color:#856404'
        if 'HIGH'     in str(v): return 'background-color:#f8d7da;color:#721c24'
        return ''
    def sv(v):
        if '🔥' in str(v): return 'background-color:#d4edda;color:#155724;font-weight:700'
        if '⚡' in str(v): return 'background-color:#fff3cd;color:#856404'
        return ''

    df_display = df_show[[c for c in show_cols if c in df_show.columns]]
    styled = (df_display.style
        .map(ss, subset=['SIGNAL'])
        .map(sr, subset=['Risk Status'])
        .map(sv, subset=['Vol Ratio'])
        .format({'LTP':'₹{:,.2f}','% Above 52W':'{:.2f}%',
                 'SL (5%)':'₹{:,.2f}','Recommended SL':'₹{:,.2f}',
                 'Risk % (EMA)':'{:.2f}%','Volume':'{:,}','Avg Vol 20D':'{:,}'}, na_rep='N/A'))

    st.markdown(f"### 📋 {len(df_display)} stocks")
    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.info("Build your **Watchlist** first, then click **🔄 RUN SIGNAL ANALYSIS**")
