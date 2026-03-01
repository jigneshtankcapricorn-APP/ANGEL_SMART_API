"""
pages/3_🧠_Signals.py
SuperTrend Signals — exact port of analyzeWatchlistSignals() AppScript.

For each WATCHLIST stock:
  • Fetch 30-day OHLC from Angel One
  • Calculate SuperTrend(10,3) → keep only GREEN stocks
  • Compute: ATR(10), EMA(23), Days Green, Flat Zone, Swing High + Date,
             Breakout, SL(5%), Recommended SL, Risk%(EMA), Risk%(5%),
             Volume Ratio, Risk Status
  • Signal: 🟢 BUY (breakout confirmed) | ⚪ WATCH (waiting)
"""
import streamlit as st
import pandas as pd
import time

from utils.angel_connect import (
    load_instrument_master,
    get_token,
    fetch_historical_ohlc,
    fetch_ltp,
)
from utils.indicators import (
    calculate_supertrend_signals,
    compute_risk,
    compute_vol_ratio,
)

# ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Signals", page_icon="🧠", layout="wide")

def require_login():
    if not st.session_state.get('connected'):
        st.warning("👈 Please **Connect to Angel One** from the Home page first.")
        st.stop()

require_login()
obj = st.session_state.angel_obj


# ──────────────────────────────────────────────────────────────────
# Load Stock Universe
# ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()


# ──────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ Signal Settings")
use_watchlist = st.sidebar.checkbox(
    "Use Watchlist stocks only", value=True,
    help="Analyse only stocks currently in your Watchlist session. "
         "Uncheck to scan all 500 stocks (slow)."
)
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Signal Logic:**  \n"
    "🟢 BUY = Breakout above Swing High + 5+ days GREEN  \n"
    "⚪ WATCH = SuperTrend GREEN, no breakout yet  \n"
    "🔴 RED stocks are excluded  \n\n"
    "**Risk Levels:**  \n"
    "🟢 LOW RISK = EMA risk ≤ 5%  \n"
    "🟡 MODERATE = 5–7%  \n"
    "⚠️ HIGH RISK = > 7%"
)


# ──────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────
st.markdown("## 🧠 SuperTrend Signals")
st.caption("SuperTrend (10, 3) · ATR (10) · EMA (23) · Swing High · BUY / WATCH")

run_btn = st.button(
    "🔄 RUN SIGNAL ANALYSIS",
    type="primary",
    use_container_width=True
)


# ──────────────────────────────────────────────────────────────────
# Stock Selection
# ──────────────────────────────────────────────────────────────────
def get_analysis_stocks():
    """
    Returns DataFrame of stocks to analyse.
    Uses Watchlist session data if available and checkbox is checked.
    Otherwise falls back to full 500-stock list.
    """
    wl = st.session_state.get('watchlist_data')
    if use_watchlist and wl is not None and not wl.empty:
        # Build compatible format from watchlist
        rows = []
        for _, r in wl.iterrows():
            rows.append({
                'name':             r['Name'],
                'symbol':           f"NSE:{r['Symbol']}",
                'sector':           r['Sector'],
                'ref_ltp':          r['LTP'],
                'w52_low':          r['52W Low'],
                'w52_high':         r.get('52W High', 0),
                'market_cap_cr':    r['Market Cap (Cr)'],
                'ref_volume':       r['Volume'],
                'ref_avg_vol_20d':  r['Avg Vol 20D'],
            })
        return pd.DataFrame(rows)
    else:
        return stocks_df.copy()


# ──────────────────────────────────────────────────────────────────
# Signal Analysis
# ──────────────────────────────────────────────────────────────────
if run_btn or 'signals_data' in st.session_state:

    if run_btn:
        st.session_state.pop('signals_data', None)

    if 'signals_data' not in st.session_state:

        analysis_stocks = get_analysis_stocks()

        if analysis_stocks.empty:
            st.warning("No stocks to analyse. Build your Watchlist first or uncheck 'Use Watchlist stocks only'.")
            st.stop()

        instruments = load_instrument_master()

        wl_hint = "Watchlist" if use_watchlist and st.session_state.get('watchlist_data') is not None else "All 500 stocks"
        st.info(f"📊 Analysing **{len(analysis_stocks)} stocks** from {wl_hint} — "
                "fetching 30-day OHLC for each…")

        results   = []
        buy_list  = []
        watch_list = []
        high_vol  = []

        prog  = st.progress(0)
        label = st.empty()

        for i, (_, row) in enumerate(analysis_stocks.iterrows()):
            sym  = row['symbol']
            name = row['name']
            label.text(f"Analysing {name} ({i+1}/{len(analysis_stocks)})…")
            prog.progress((i + 1) / len(analysis_stocks))

            token = get_token(instruments, sym)
            if not token:
                continue

            trading_sym = sym.replace('NSE:', '')

            # ── Fetch Live LTP ──
            ltp = fetch_ltp(obj, 'NSE', trading_sym, token)
            if not ltp:
                ltp = row['ref_ltp']

            # ── Fetch 30-day OHLC ──
            ohlc = fetch_historical_ohlc(obj, token, 'NSE', days=40)

            if not ohlc or len(ohlc) < 15:
                time.sleep(0.15)
                continue

            # Update last close with live LTP
            if ohlc:
                ohlc[-1]['close'] = ltp

            # ── SuperTrend Analysis ──
            sig = calculate_supertrend_signals(ohlc, period=10, multiplier=3)

            # Only GREEN stocks shown (mirrors AppScript)
            if sig['supertrend_status'] != '🟢 GREEN':
                time.sleep(0.1)
                continue

            # ── Volume ──
            volume      = ohlc[-1]['volume'] if ohlc else row['ref_volume']
            avg_vol_20d = (
                sum(c['volume'] for c in ohlc[-21:-1]) / 20
                if len(ohlc) >= 21
                else row['ref_avg_vol_20d']
            )
            vol_ratio, vol_label = compute_vol_ratio(volume, avg_vol_20d)
            if vol_ratio >= 1.5:
                high_vol.append(f"{trading_sym} ({vol_ratio:.1f}x)")

            # ── Risk ──
            risk = compute_risk(ltp, sig['ema23'])

            # ── Signal ──
            signal = '🟢 BUY' if sig['is_breakout'] else '⚪ WATCH'
            if signal == '🟢 BUY':
                buy_list.append(trading_sym)
            else:
                watch_list.append(trading_sym)

            # ── % Above 52W Low ──
            w52_low = row['w52_low']
            pct_above = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0

            results.append({
                'Symbol':            trading_sym,
                'Sector':            row['sector'],
                'LTP':               round(ltp, 2),
                '52W Low':           round(w52_low, 2),
                '% Above 52W':       round(pct_above, 2),
                'Days Green':        sig['days_green'],
                'Flat Zone?':        '✅ YES' if sig['is_flat'] else '❌ NO',
                'Swing High':        sig['swing_high'] or 'N/A',
                'Date of Swing High':sig['swing_high_date'] or 'N/A',
                'Breakout?':         '✅ YES' if sig['is_breakout'] else '❌ NO',
                '23-EMA':            sig['ema23'] or 'N/A',
                'SL (5%)':           risk['sl_5pct'],
                'Recommended SL':    risk['recommended_sl'],
                'Risk % (EMA)':      risk['risk_ema_pct'],
                'Risk % (5%)':       risk['risk_pct_5'],
                'Volume':            int(volume),
                'Avg Vol 20D':       int(avg_vol_20d),
                'Vol Ratio':         vol_label,
                '_vol_ratio_num':    vol_ratio,
                '_risk_ema':         risk['risk_ema_pct'],
                'Risk Status':       risk['risk_status'],
                'SIGNAL':            signal,
            })

            time.sleep(0.15)

        prog.empty()
        label.empty()

        df_sig = pd.DataFrame(results) if results else pd.DataFrame()
        st.session_state.signals_data  = df_sig
        st.session_state.signals_meta  = {
            'buy': buy_list,
            'watch': watch_list,
            'high_vol': high_vol,
            'total_analysed': len(analysis_stocks),
        }

    # ── Display ──────────────────────────────────────────────────
    df_sig = st.session_state.signals_data
    meta   = st.session_state.get('signals_meta', {})

    if df_sig is None or df_sig.empty:
        st.warning("No GREEN SuperTrend stocks found in the analysed universe.")
        st.stop()

    # ── Summary Metrics ──
    buy_n   = len(meta.get('buy', []))
    watch_n = len(meta.get('watch', []))
    hvol_n  = len(meta.get('high_vol', []))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Analysed",    meta.get('total_analysed', '—'))
    m2.metric("🟢 GREEN Stocks",   len(df_sig))
    m3.metric("🟢 BUY Signals",    buy_n)
    m4.metric("⚪ WATCH Signals",  watch_n)
    m5.metric("🔥 High Volume",    hvol_n)

    # ── BUY Alert Banner ──
    if meta.get('buy'):
        st.success(
            f"🟢 **BUY SIGNALS (Breakout Confirmed):** "
            + ", ".join(meta['buy'])
        )
    if meta.get('high_vol'):
        st.error(
            f"🔥 **HIGH VOLUME STOCKS (≥ 1.5× Avg):** "
            + ", ".join(meta['high_vol'])
        )

    st.markdown("---")

    # ── Filter Controls ──
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_signal = st.multiselect(
            "Filter by Signal",
            options=['🟢 BUY', '⚪ WATCH'],
            default=['🟢 BUY', '⚪ WATCH']
        )
    with col_f2:
        filter_risk = st.multiselect(
            "Filter by Risk",
            options=['🟢 LOW RISK', '🟡 MODERATE', '⚠️ HIGH RISK'],
            default=['🟢 LOW RISK', '🟡 MODERATE', '⚠️ HIGH RISK']
        )

    df_show = df_sig[
        df_sig['SIGNAL'].isin(filter_signal) &
        df_sig['Risk Status'].isin(filter_risk)
    ].copy()

    # ── Colour Styling ──
    DISPLAY_COLS = [
        'Symbol', 'Sector', 'LTP', '% Above 52W',
        'Days Green', 'Flat Zone?', 'Swing High', 'Date of Swing High',
        'Breakout?', '23-EMA', 'SL (5%)', 'Recommended SL',
        'Risk % (EMA)', 'Risk % (5%)',
        'Volume', 'Avg Vol 20D', 'Vol Ratio',
        'Risk Status', 'SIGNAL'
    ]

    df_display = df_show[[c for c in DISPLAY_COLS if c in df_show.columns]].copy()

    def style_signal(val):
        if val == '🟢 BUY':
            return 'background-color:#28a745;color:white;font-weight:700'
        if val == '⚪ WATCH':
            return 'background-color:#ffc107;color:black;font-weight:700'
        return ''

    def style_risk(val):
        if 'LOW RISK' in str(val):
            return 'background-color:#d4edda;color:#155724'
        if 'MODERATE' in str(val):
            return 'background-color:#fff3cd;color:#856404'
        if 'HIGH RISK' in str(val):
            return 'background-color:#f8d7da;color:#721c24'
        return ''

    def style_vol(val):
        if '🔥' in str(val):
            return 'background-color:#d4edda;color:#155724;font-weight:700'
        if '⚡' in str(val):
            return 'background-color:#fff3cd;color:#856404'
        return ''

    def style_days_green(val):
        try:
            v = int(val)
            if v >= 3: return 'background-color:#d4edda;color:#155724;font-weight:700'
        except Exception:
            pass
        return ''

    def style_breakout(val):
        if val == '✅ YES':
            return 'background-color:#d4edda;color:#155724;font-weight:700'
        return ''

    styled = (
        df_display.style
        .applymap(style_signal,    subset=['SIGNAL'])
        .applymap(style_risk,      subset=['Risk Status'])
        .applymap(style_vol,       subset=['Vol Ratio'])
        .applymap(style_days_green,subset=['Days Green'])
        .applymap(style_breakout,  subset=['Breakout?'])
        .format({
            'LTP':           '₹{:,.2f}',
            '% Above 52W':  '{:.2f}%',
            'Swing High':    lambda x: f'₹{x:,.2f}' if isinstance(x, (int, float)) else x,
            '23-EMA':        lambda x: f'₹{x:,.2f}' if isinstance(x, (int, float)) else x,
            'SL (5%)':       '₹{:,.2f}',
            'Recommended SL':'₹{:,.2f}',
            'Risk % (EMA)':  '{:.2f}%',
            'Risk % (5%)':   '{:.2f}%',
            'Volume':        '{:,}',
            'Avg Vol 20D':   '{:,}',
        }, na_rep='N/A')
    )

    st.markdown(f"### 📋 Signals Table — {len(df_display)} stocks")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Legend ──
    st.markdown("---")
    st.markdown("""
**Signal Logic (exact AppScript replication):**
- 🟢 **BUY** = LTP broke above Swing High + last candle bullish + 5+ days GREEN
- ⚪ **WATCH** = SuperTrend GREEN, waiting for breakout
- **Swing High** = Highest point after RED→GREEN transition (frozen after 7 days, excludes today)
- **Flat Zone** = SuperTrend range < 3.5% over 5+ consecutive green days
- **Recommended SL** = max(23-EMA, 5%-SL)
- **Risk %** = (LTP − 23-EMA) / LTP × 100
    """)

else:
    st.info(
        "Click **🔄 RUN SIGNAL ANALYSIS** to start.  \n\n"
        "**Tip:** Build your Watchlist first (📋 Watchlist page), then run "
        "Signals on the filtered stocks for faster results."
    )
    st.markdown("""
**What this page does:**
1. Fetches 30-day daily OHLC for each stock from Angel One
2. Calculates SuperTrend (10, 3) — same formula as your AppScript
3. Keeps only GREEN stocks
4. Computes Swing High, Flat Zone, Breakout, EMA(23), Risk
5. Labels each stock 🟢 BUY or ⚪ WATCH

**Columns match your Google Sheet SIGNALS tab exactly — 20 columns.**
    """)
