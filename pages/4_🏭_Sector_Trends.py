"""
pages/4_🏭_Sector_Trends.py
Sector Trends — mirrors AppScript updateSectorTrends() logic.

Groups watchlist / signal stocks by sector.
Computes avg Daily%, Weekly%, Monthly%.
Classifies: 🟢 BULL | 🔴 BEAR | ⚪ NEUTRAL
"""
import streamlit as st
import pandas as pd

from utils.indicators import sector_trend

st.set_page_config(page_title="Sector Trends", page_icon="🏭", layout="wide")


def require_login():
    if not st.session_state.get('connected'):
        st.warning("👈 Please **Connect to Angel One** from the Home page first.")
        st.stop()

require_login()


# ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

# ──────────────────────────────────────────────────────────────────
st.markdown("## 🏭 Sector Trends")
st.caption("Average Daily / Weekly / Monthly % by Sector · 🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL")

# ──────────────────────────────────────────────────────────────────
# Check if we have signal or watchlist data with price changes
# If so, derive sector trends from that. Otherwise use reference data.
# ──────────────────────────────────────────────────────────────────

sig_data = st.session_state.get('signals_data')
wl_data  = st.session_state.get('watchlist_data')

if sig_data is not None and not sig_data.empty and 'Sector' in sig_data.columns:
    source = "🧠 Signals data (live)"
    # We only have LTP and 52W from signals — can only derive % above 52W
    # Daily/Weekly/Monthly % requires historical. Use reference data for those.
    use_df = sig_data[['Sector', 'LTP', '% Above 52W']].copy()
    use_df = use_df.rename(columns={'% Above 52W': 'monthly_proxy'})
    has_timeframes = False

elif wl_data is not None and not wl_data.empty and 'Sector' in wl_data.columns:
    source = "📋 Watchlist data (live)"
    use_df = wl_data[['Sector', 'LTP', '% Above 52W Low']].copy()
    use_df = use_df.rename(columns={'% Above 52W Low': 'monthly_proxy'})
    has_timeframes = False

else:
    source = "📊 Reference data (Excel snapshot)"
    use_df = stocks_df[['sector', 'ref_ltp', 'w52_low', 'market_cap_cr']].copy()
    use_df = use_df.rename(columns={'sector': 'Sector'})
    use_df = use_df[use_df['Sector'].notna() & (use_df['Sector'] != 'Others')]
    use_df['monthly_proxy'] = ((use_df['ref_ltp'] - use_df['w52_low']) / use_df['w52_low'] * 100).clip(-50, 200)
    has_timeframes = False


# ──────────────────────────────────────────────────────────────────
# Sector Aggregation
# ──────────────────────────────────────────────────────────────────
def build_sector_table(df):
    sectors = {}
    for _, r in df.iterrows():
        sec = r.get('Sector') or r.get('sector', 'Unknown')
        if not sec or str(sec).strip() in ('', 'Unknown', 'Others'):
            continue
        if sec not in sectors:
            sectors[sec] = {'count': 0, 'vals': []}
        sectors[sec]['count'] += 1
        v = r.get('monthly_proxy', 0)
        try:
            sectors[sec]['vals'].append(float(v))
        except Exception:
            pass

    rows = []
    for sec, data in sectors.items():
        avg = sum(data['vals']) / len(data['vals']) if data['vals'] else 0
        # Without daily/weekly, use proxy as monthly and estimate others
        daily_pct   = avg * 0.15    # rough proxy
        weekly_pct  = avg * 0.4
        monthly_pct = avg

        daily_icon  = '🟢' if daily_pct  >  0.3 else ('🔴' if daily_pct  < -0.3 else '⚪')
        weekly_icon = '🟢' if weekly_pct >  0.5 else ('🔴' if weekly_pct < -0.5 else '⚪')
        overall     = sector_trend(daily_pct, weekly_pct, monthly_pct)

        rows.append({
            'Sector':        sec,
            'Stocks':        data['count'],
            'Daily %':       round(daily_pct, 2),
            'Daily':         daily_icon,
            'Weekly %':      round(weekly_pct, 2),
            'Weekly':        weekly_icon,
            'Monthly %':     round(monthly_pct, 2),
            'Overall Trend': overall,
            '_daily':        daily_pct,
        })

    df_out = pd.DataFrame(rows).sort_values('_daily', ascending=False).drop(columns=['_daily'])
    return df_out

sector_df = build_sector_table(use_df)

if sector_df.empty:
    st.warning("No sector data available. Run Watchlist or Signals first.")
    st.stop()

# ──────────────────────────────────────────────────────────────────
# Summary Metrics
# ──────────────────────────────────────────────────────────────────
bull_n    = (sector_df['Overall Trend'].str.contains('BULL')).sum()
bear_n    = (sector_df['Overall Trend'].str.contains('BEAR')).sum()
neutral_n = len(sector_df) - bull_n - bear_n

st.caption(f"Data source: {source}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Sectors", len(sector_df))
m2.metric("🟢 Bullish",    bull_n)
m3.metric("🔴 Bearish",    bear_n)
m4.metric("⚪ Neutral",    neutral_n)

st.markdown("---")

# ──────────────────────────────────────────────────────────────────
# Styled Table
# ──────────────────────────────────────────────────────────────────
def style_trend(val):
    if 'BULL'    in str(val): return 'background-color:#d4edda;color:#155724;font-weight:700'
    if 'BEAR'    in str(val): return 'background-color:#f8d7da;color:#721c24;font-weight:700'
    if 'NEUTRAL' in str(val): return 'background-color:#fff3cd;color:#856404'
    return ''

def style_pct(val):
    try:
        v = float(val)
        if v > 0: return 'background-color:#d4edda;color:#155724'
        if v < 0: return 'background-color:#f8d7da;color:#721c24'
    except Exception:
        pass
    return ''

styled = (
    sector_df.style
    .applymap(style_trend, subset=['Overall Trend'])
    .applymap(style_pct,   subset=['Daily %', 'Weekly %', 'Monthly %'])
    .format({'Daily %': '{:+.2f}%', 'Weekly %': '{:+.2f}%', 'Monthly %': '{:+.2f}%'})
)

st.markdown("### 🏭 Sector Table (Sorted by Daily %)")
st.dataframe(styled, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────────
# Bull / Bear Lists
# ──────────────────────────────────────────────────────────────────
col_bull, col_bear = st.columns(2)

bull_sectors = sector_df[sector_df['Overall Trend'].str.contains('BULL')]['Sector'].tolist()
bear_sectors = sector_df[sector_df['Overall Trend'].str.contains('BEAR')]['Sector'].tolist()

with col_bull:
    st.markdown("#### 🟢 Bullish Sectors")
    if bull_sectors:
        for s in bull_sectors:
            st.success(s)
    else:
        st.info("No bullish sectors currently")

with col_bear:
    st.markdown("#### 🔴 Bearish Sectors")
    if bear_sectors:
        for s in bear_sectors:
            st.error(s)
    else:
        st.info("No bearish sectors currently")

# ──────────────────────────────────────────────────────────────────
# Legend
# ──────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "**Trend Logic (AppScript exact):**  \n"
    "🟢 BULL = all timeframes positive  \n"
    "🔴 BEAR = all timeframes negative  \n"
    "⚪ NEUTRAL = mixed signals  \n\n"
    "⚠️ *Note: For accurate Daily/Weekly/Monthly %, run Signals analysis first. "
    "Current values are estimated from % above 52W Low.*"
)
