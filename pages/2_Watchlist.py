import streamlit as st
import pandas as pd
import time
from datetime import datetime, time as dtime
import pytz

st.set_page_config(page_title="📋 Watchlist", page_icon="📋", layout="wide")

for k in ['connected', 'angel_obj', 'user_data']:
    if k not in st.session_state:
        st.session_state[k] = False if k == 'connected' else None

def market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    return dtime(9,15) <= now.time() <= dtime(15,30)

# ── sidebar ────────────────────────────────────────────────────────
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

    st.subheader("⚙️ Filters")
    min_pct  = st.number_input("Min % Above 52W Low", 0.0, 100.0, 10.0, 0.5)
    max_pct  = st.number_input("Max % Above 52W Low", 0.0, 100.0, 15.0, 0.5)
    min_mcap = st.number_input("Min Market Cap (Cr)",  500.0, value=500.0, step=100.0)
    if min_mcap < 500: min_mcap = 500.0
    st.caption("🟢 STRONG ≤12% · 🟡 MOD 12-15% · 🟠 WATCH >15%")

# ── page guard ─────────────────────────────────────────────────────
if not st.session_state.connected:
    st.warning("👈 Please **login from the sidebar** to use Watchlist.", icon="🔑")
    st.stop()

# ── page content ───────────────────────────────────────────────────
from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import compute_vol_ratio

st.title("📋 Watchlist")
st.caption(f"Filter: {min_pct}–{max_pct}% above 52W Low · Min ₹{min_mcap:,.0f} Cr")

run_btn = st.button("🔄 FETCH WATCHLIST", type="primary", use_container_width=True)

@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv('data/stocks.csv')

stocks_df = load_stocks()

def get_status(pct):
    if pct <= 12: return '🟢 STRONG'
    if pct <= 15: return '🟡 MODERATE'
    return '🟠 WATCH'

if run_btn:
    st.session_state.pop('watchlist_data', None)

if run_btn or 'watchlist_data' in st.session_state:
    if 'watchlist_data' not in st.session_state:
        obj = st.session_state.angel_obj
        df = stocks_df.copy()
        df = df[(df['ref_ltp'] > 0) & (df['w52_low'] > 0) & (df['market_cap_cr'] >= min_mcap)].copy()
        df['ref_pct'] = (df['ref_ltp'] - df['w52_low']) / df['w52_low'] * 100
        candidates = df[(df['ref_pct'] >= min_pct) & (df['ref_pct'] <= max_pct)].reset_index(drop=True)

        if candidates.empty:
            st.warning("No stocks found with these filters. Try widening the range.")
            st.stop()

        st.info(f"📊 {len(candidates)} candidates found — fetching live data from Angel One…")
        instruments = load_instrument_master()
        results = []
        prog  = st.progress(0)
        status_text = st.empty()

        for i, (_, row) in enumerate(candidates.iterrows()):
            sym = row['symbol']
            status_text.text(f"⏳ {row['name']} ({i+1}/{len(candidates)})")
            prog.progress((i+1) / len(candidates))

            token = get_token(instruments, sym)
            if not token: continue

            tsym = sym.replace('NSE:', '')
            ltp  = fetch_ltp(obj, 'NSE', tsym, token) or row['ref_ltp']

            hist = fetch_historical_ohlc(obj, token, 'NSE', days=30)
            if hist and len(hist) >= 2:
                vol     = hist[-1]['volume']
                avg_vol = sum(h['volume'] for h in hist[-21:-1]) / 20 if len(hist) >= 21 else row['ref_avg_vol_20d']
            else:
                vol, avg_vol = row['ref_volume'], row['ref_avg_vol_20d']

            w52l    = row['w52_low']
            pct_ab  = ((ltp - w52l) / w52l * 100) if w52l > 0 else 0
            vr, vl  = compute_vol_ratio(vol, avg_vol)

            results.append({
                'Name': row['name'], 'Symbol': tsym, 'Sector': row['sector'],
                'LTP': round(ltp, 2), '52W Low': round(w52l, 2),
                '% Above 52W': round(pct_ab, 2),
                'Mkt Cap (Cr)': round(row['market_cap_cr'], 0),
                'Volume': int(vol), 'Avg Vol 20D': int(avg_vol),
                'Vol Ratio': vl, '_vr': vr,
                'Status': get_status(pct_ab),
            })
            time.sleep(0.15)

        prog.empty(); status_text.empty()

        df_r = pd.DataFrame(results) if results else pd.DataFrame()
        if not df_r.empty:
            df_r = df_r[
                (df_r['% Above 52W'] >= min_pct) &
                (df_r['% Above 52W'] <= max_pct) &
                (df_r['Mkt Cap (Cr)'] >= min_mcap)
            ].sort_values('% Above 52W').reset_index(drop=True)
        st.session_state.watchlist_data = df_r

    df_r = st.session_state.get('watchlist_data', pd.DataFrame())
    if df_r is None or df_r.empty:
        st.warning("No stocks matched after live check.")
        st.stop()

    strong = (df_r['Status'] == '🟢 STRONG').sum()
    mod    = (df_r['Status'] == '🟡 MODERATE').sum()
    wtch   = (df_r['Status'] == '🟠 WATCH').sum()
    vbk    = (df_r['_vr'] >= 1.5).sum()

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total",       len(df_r))
    c2.metric("🟢 STRONG",  strong)
    c3.metric("🟡 MODERATE",mod)
    c4.metric("🟠 WATCH",   wtch)
    c5.metric("🔥 Vol Brk", vbk)

    vb = df_r[df_r['_vr'] >= 1.5]
    if not vb.empty:
        st.error("🔥 VOLUME BREAKOUT: " + " · ".join(f"{r['Symbol']} ({r['Vol Ratio']})" for _,r in vb.iterrows()))

    st.divider()

    def cs(v):
        if 'STRONG'   in str(v): return 'background:#d4edda;color:#155724;font-weight:700'
        if 'MODERATE' in str(v): return 'background:#fff3cd;color:#856404;font-weight:700'
        if 'WATCH'    in str(v): return 'background:#ffe5d0;color:#7d4e00'
        return ''
    def cv(v):
        if '🔥' in str(v): return 'background:#d4edda;color:#155724;font-weight:700'
        if '⚡' in str(v): return 'background:#fff3cd;color:#856404'
        return ''

    show = ['Name','Symbol','Sector','LTP','52W Low','% Above 52W','Mkt Cap (Cr)','Volume','Avg Vol 20D','Vol Ratio','Status']
    styled = (df_r[show].style
        .map(cs, subset=['Status'])
        .map(cv, subset=['Vol Ratio'])
        .format({'LTP':'₹{:,.2f}','52W Low':'₹{:,.2f}',
                 '% Above 52W':'{:.2f}%','Mkt Cap (Cr)':'{:,.0f}',
                 'Volume':'{:,}','Avg Vol 20D':'{:,}'}))
    st.dataframe(styled, use_container_width=True, hide_index=True)

else:
    st.info("Set filters in the sidebar → click **🔄 FETCH WATCHLIST**")
    st.markdown("""
**What this does:**
- Uses reference 52W Low from your Excel to pre-filter candidates
- Fetches **live LTP** from Angel One for each stock
- Fetches **30-day history** to calculate volume ratio
- Shows 🔥 Volume Breakout stocks (Volume > 1.5× 20-day average)
""")
