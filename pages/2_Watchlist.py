"""
pages/2_📋_Watchlist.py
Watchlist — mirrors AppScript createWatchlist / updateWatchlist logic.

Filters:
  • % above 52W Low  (min / max slider)
  • Min Market Cap   (≥ 500 Cr)
  • Volume Ratio     (highlighted ≥ 1.5×)
Sorted: ascending % above 52W Low
Status: 🟢 STRONG (≤12%), 🟡 MODERATE (12–15%), 🟠 WATCH (>15%)
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
from utils.indicators import compute_vol_ratio

# ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Watchlist", page_icon="📋", layout="wide")

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
# Sidebar Filters (mirrors AppScript filter settings)
# ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ Filter Settings")

min_pct = st.sidebar.number_input(
    "Min % Above 52W Low", min_value=0.0, max_value=100.0, value=10.0, step=0.5)
max_pct = st.sidebar.number_input(
    "Max % Above 52W Low", min_value=0.0, max_value=100.0, value=15.0, step=0.5)
min_mcap = st.sidebar.number_input(
    "Min Market Cap (Cr)", min_value=500.0, value=500.0, step=100.0)

# Enforce minimum ₹500 Cr (AppScript rule)
if min_mcap < 500:
    min_mcap = 500.0
    st.sidebar.warning("Min Market Cap enforced to ₹500 Cr")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Status Legend:**  \n"
    "🟢 STRONG = ≤12% above 52W Low  \n"
    "🟡 MODERATE = 12–15%  \n"
    "🟠 WATCH = >15%  \n"
    "🔥 VOL BREAKOUT = Vol ≥ 1.5× Avg"
)


# ──────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────
st.markdown("## 📋 Watchlist")
st.caption(f"Filter: {min_pct}–{max_pct}% above 52W Low · Min Market Cap: ₹{min_mcap:,.0f} Cr")

run_btn = st.button(
    "🔄 FETCH / REFRESH WATCHLIST",
    type="primary",
    use_container_width=True
)

# ──────────────────────────────────────────────────────────────────
# Pre-filter using cached (reference) data for efficiency
# ──────────────────────────────────────────────────────────────────
def pre_filter(df, min_pct, max_pct, min_mcap):
    """
    Quick filter on reference data before making API calls.
    Uses ref_ltp and w52_low (from Excel) for a fast candidate list.
    """
    d = df.copy()
    d = d[(d['ref_ltp'] > 0) & (d['w52_low'] > 0) & (d['market_cap_cr'] >= min_mcap)]
    d['ref_pct_above'] = ((d['ref_ltp'] - d['w52_low']) / d['w52_low']) * 100
    d = d[(d['ref_pct_above'] >= min_pct) & (d['ref_pct_above'] <= max_pct)]
    return d.reset_index(drop=True)


def watchlist_status(pct):
    if pct <= 12:
        return '🟢 STRONG'
    elif pct <= 15:
        return '🟡 MODERATE'
    return '🟠 WATCH'


# ──────────────────────────────────────────────────────────────────
# Main: Fetch Live Data & Build Watchlist
# ──────────────────────────────────────────────────────────────────
if run_btn or 'watchlist_data' in st.session_state:

    if run_btn:
        # Clear old data
        st.session_state.pop('watchlist_data', None)

    if 'watchlist_data' not in st.session_state:

        candidates = pre_filter(stocks_df, min_pct, max_pct, min_mcap)

        if candidates.empty:
            st.warning(f"No candidates found with {min_pct}–{max_pct}% above 52W Low "
                       f"and Market Cap ≥ ₹{min_mcap:,.0f} Cr (using reference data).")
            st.stop()

        st.info(f"📊 {len(candidates)} candidate stocks found (using reference data). "
                f"Now fetching live prices from Angel One…")

        instruments = load_instrument_master()
        results = []
        errors  = []

        prog  = st.progress(0)
        label = st.empty()

        for idx, row in candidates.iterrows():
            sym   = row['symbol']             # e.g. 'NSE:RELIANCE'
            label.text(f"Fetching {row['name']} ({idx+1}/{len(candidates)})…")
            prog.progress((idx + 1) / len(candidates))

            token = get_token(instruments, sym)
            if not token:
                errors.append(sym)
                continue

            trading_sym = sym.replace('NSE:', '')

            # ── Live LTP ──
            ltp = fetch_ltp(obj, 'NSE', trading_sym, token)
            if not ltp:
                ltp = row['ref_ltp']   # fallback to reference

            # ── 52W Low (use reference; live via 365-day history is slow) ──
            w52_low  = row['w52_low']
            w52_high = row['w52_high']

            # ── Volume: fetch 25-day history for avg vol ──
            history = fetch_historical_ohlc(obj, token, 'NSE', days=30)
            if history:
                volume      = history[-1]['volume']
                avg_vol_20d = sum(h['volume'] for h in history[-21:-1]) / 20 if len(history) >= 21 else row['ref_avg_vol_20d']
            else:
                volume      = row['ref_volume']
                avg_vol_20d = row['ref_avg_vol_20d']

            pct_above = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0
            vol_ratio, vol_label = compute_vol_ratio(volume, avg_vol_20d)
            status = watchlist_status(pct_above)
            mcap   = row['market_cap_cr']

            results.append({
                'Name':            row['name'],
                'Symbol':          trading_sym,
                'Sector':          row['sector'],
                'LTP':             round(ltp, 2),
                '52W Low':         round(w52_low, 2),
                '52W High':        round(w52_high, 2),
                '% Above 52W Low': round(pct_above, 2),
                'Market Cap (Cr)': round(mcap, 0),
                'Volume':          int(volume),
                'Avg Vol 20D':     int(avg_vol_20d),
                'Vol Ratio':       vol_label,
                'Vol Ratio Num':   vol_ratio,
                'Status':          status,
            })

            time.sleep(0.15)  # Angel One rate limit buffer

        prog.empty()
        label.empty()

        df_result = pd.DataFrame(results)
        if not df_result.empty:
            # Re-apply live filter (ref data was an estimate)
            df_result = df_result[
                (df_result['% Above 52W Low'] >= min_pct) &
                (df_result['% Above 52W Low'] <= max_pct) &
                (df_result['Market Cap (Cr)'] >= min_mcap)
            ].sort_values('% Above 52W Low').reset_index(drop=True)

        st.session_state.watchlist_data = df_result
        st.session_state.watchlist_params = (min_pct, max_pct, min_mcap)

    # ── Display ──────────────────────────────────────────────────
    df_result = st.session_state.watchlist_data

    if df_result.empty:
        st.warning("No stocks matched the filters after live price check.")
        st.stop()

    # ── Summary Metrics ──
    strong   = (df_result['Status'] == '🟢 STRONG').sum()
    moderate = (df_result['Status'] == '🟡 MODERATE').sum()
    watch    = (df_result['Status'] == '🟠 WATCH').sum()
    vol_brk  = (df_result['Vol Ratio Num'] >= 1.5).sum()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Found",       len(df_result))
    m2.metric("🟢 STRONG (≤12%)", strong)
    m3.metric("🟡 MODERATE",      moderate)
    m4.metric("🟠 WATCH",         watch)
    m5.metric("🔥 Vol Breakouts",  vol_brk)

    st.markdown("---")

    # ── Volume Breakout Alert ──
    vb_stocks = df_result[df_result['Vol Ratio Num'] >= 1.5]
    if not vb_stocks.empty:
        names = ', '.join(
            f"{r['Symbol']} ({r['Vol Ratio']})"
            for _, r in vb_stocks.iterrows()
        )
        st.error(f"🔥 **VOLUME BREAKOUT STOCKS** (Vol ≥ 1.5× Avg): {names}")

    # ── Main Table ──
    st.markdown("### 📊 Watchlist Stocks")

    display_cols = [
        'Name', 'Symbol', 'Sector', 'LTP', '52W Low',
        '% Above 52W Low', 'Market Cap (Cr)',
        'Volume', 'Avg Vol 20D', 'Vol Ratio', 'Status'
    ]
    df_show = df_result[display_cols].copy()

    # ── Colour formatting via st.dataframe with column config ──
    def colour_status(val):
        if 'STRONG'   in str(val): return 'background-color:#d4edda;color:#155724;font-weight:700'
        if 'MODERATE' in str(val): return 'background-color:#fff3cd;color:#856404;font-weight:700'
        if 'WATCH'    in str(val): return 'background-color:#f8d7da;color:#721c24'
        return ''

    def colour_vol(val):
        if '🔥' in str(val): return 'background-color:#d4edda;color:#155724;font-weight:700'
        if '⚡' in str(val): return 'background-color:#fff3cd;color:#856404'
        return ''

    styled = (
        df_show.style
        .applymap(colour_status, subset=['Status'])
        .applymap(colour_vol,    subset=['Vol Ratio'])
        .format({
            'LTP':             '₹{:,.2f}',
            '52W Low':         '₹{:,.2f}',
            '% Above 52W Low': '{:.2f}%',
            'Market Cap (Cr)': '{:,.0f}',
            'Volume':          '{:,}',
            'Avg Vol 20D':     '{:,}',
        })
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Sector Breakdown ──
    st.markdown("### 🏭 By Sector")
    sector_grp = (
        df_result.groupby('Sector')
        .agg(Count=('Name', 'count'),
             Avg_Pct=('% Above 52W Low', 'mean'))
        .sort_values('Count', ascending=False)
        .reset_index()
    )
    sector_grp['Avg_Pct'] = sector_grp['Avg_Pct'].apply(lambda x: f"{x:.2f}%")
    st.dataframe(sector_grp, use_container_width=True, hide_index=True)

    st.caption(
        "💡 Prices fetched live from Angel One SmartAPI. "
        "Market Cap is pre-loaded from reference data (Google Finance snapshot)."
    )

else:
    st.info(
        "⚙️ Set your filter parameters on the left sidebar, "
        "then click **🔄 FETCH / REFRESH WATCHLIST** to load live data."
    )
    st.markdown("""
    **How it works:**
    1. Reference 52W Low data pre-loaded from your Excel snapshot
    2. Live LTP fetched from Angel One for each candidate stock
    3. Historical data (30 days) fetched for volume ratio calculation
    4. All filter logic mirrors your AppScript `updateWatchlist()` exactly
    """)
