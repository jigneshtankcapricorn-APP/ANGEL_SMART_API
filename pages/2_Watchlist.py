import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz

st.set_page_config(page_title="📋 Watchlist", page_icon="📋", layout="wide")

from utils.sidebar import render_sidebar, require_app_login
from utils import data_store

require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import compute_vol_ratio

st.title("📋 Watchlist")

# ── Sidebar filters ───────────────────────────────────────────────
with st.sidebar:
    st.subheader("⚙️ Filters")
    min_pct  = st.number_input("Min % Above 52W Low", 0.0, 200.0, 10.0, 0.5)
    max_pct  = st.number_input("Max % Above 52W Low", 0.0, 200.0, 15.0, 0.5)
    min_mcap = st.number_input("Min Market Cap (Cr)",  0.0, value=500.0, step=100.0)
    sector_filter = st.multiselect("Sector Filter (optional)", [], placeholder="All sectors")
    st.caption("🟢 STRONG ≤12% · 🟡 MOD 12-15% · 🟠 WATCH >15%")

# ── Load full stock universe (2242 stocks from Excel) ─────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    try:
        df = pd.read_csv("data/stocks_full.csv")
    except FileNotFoundError:
        df = pd.read_csv("data/stocks.csv")
    return df

stocks_df = load_stocks()

# Populate sector filter dynamically
all_sectors = sorted(stocks_df["sector"].dropna().unique().tolist())
all_sectors = [s for s in all_sectors if s and s != "Unknown"]
with st.sidebar:
    sector_filter = st.multiselect("Sector Filter (optional)", all_sectors, placeholder="All sectors")

st.caption(f"Universe: **{len(stocks_df):,} stocks** from Excel list")

# ── Persistent data display ───────────────────────────────────────
cached_df   = data_store.load("watchlist_df")
cached_time = data_store.load("last_watchlist")

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_btn = st.button("🔄 FETCH WATCHLIST", type="primary", use_container_width=True)
with col_info:
    if cached_time:
        st.info(f"📦 Last fetched: **{cached_time}** — data saved, no refresh needed.")

def get_status(pct):
    if pct <= 12: return "🟢 STRONG"
    if pct <= 15: return "🟡 MODERATE"
    return "🟠 WATCH"

# ── Fetch ─────────────────────────────────────────────────────────
if run_btn:
    obj = st.session_state.angel_obj

    df = stocks_df.copy()
    # Apply sector filter
    if sector_filter:
        df = df[df["sector"].isin(sector_filter)]
    # Apply mcap filter (only for stocks with known mcap)
    df_has_mcap = df[df["market_cap_cr"] > 0]
    df_no_mcap  = df[df["market_cap_cr"] == 0]
    df_has_mcap = df_has_mcap[df_has_mcap["market_cap_cr"] >= min_mcap]
    df = pd.concat([df_has_mcap, df_no_mcap], ignore_index=True)

    # Pre-filter by ref_pct from reference data (only where ref_ltp and w52_low known)
    df_known  = df[(df["ref_ltp"] > 0) & (df["w52_low"] > 0)].copy()
    df_unknown = df[(df["ref_ltp"] == 0) | (df["w52_low"] == 0)].copy()
    df_known["ref_pct"] = (df_known["ref_ltp"] - df_known["w52_low"]) / df_known["w52_low"] * 100
    candidates_known  = df_known[(df_known["ref_pct"] >= min_pct) & (df_known["ref_pct"] <= max_pct)]
    # For unknown ref data, include them so we can check live
    candidates = pd.concat([candidates_known, df_unknown.head(200)], ignore_index=True)

    if candidates.empty:
        st.warning("No stocks found with these filters. Try widening the range.")
        st.stop()

    st.info(f"📊 {len(candidates)} candidates — fetching live data from Angel One…")
    instruments = load_instrument_master()
    results = []
    prog    = st.progress(0)
    status_text = st.empty()

    for i, (_, row) in enumerate(candidates.iterrows()):
        sym = str(row["symbol"]).replace("NSE:", "")
        status_text.text(f"⏳ {row['name']} ({i+1}/{len(candidates)})")
        prog.progress((i+1) / len(candidates))

        token = get_token(instruments, sym)
        if not token:
            time.sleep(0.05); continue

        ltp = fetch_ltp(obj, "NSE", sym, token) or row.get("ref_ltp", 0)
        if not ltp or ltp == 0:
            time.sleep(0.05); continue

        hist = fetch_historical_ohlc(obj, token, "NSE", days=30)
        if hist and len(hist) >= 2:
            vol     = hist[-1]["volume"]
            avg_vol = sum(h["volume"] for h in hist[-21:-1]) / 20 if len(hist) >= 21 else row.get("ref_avg_vol_20d", 0)
        else:
            vol, avg_vol = row.get("ref_volume", 0), row.get("ref_avg_vol_20d", 0)

        w52l   = row.get("w52_low", 0)
        pct_ab = ((ltp - w52l) / w52l * 100) if w52l > 0 else 0
        vr, vl = compute_vol_ratio(vol, avg_vol)

        results.append({
            "Name":          row["name"],
            "Symbol":        sym,
            "Sector":        row.get("sector", "Unknown"),
            "LTP":           round(ltp, 2),
            "52W Low":       round(w52l, 2),
            "% Above 52W":   round(pct_ab, 2),
            "Mkt Cap (Cr)":  round(row.get("market_cap_cr", 0), 0),
            "Volume":        int(vol),
            "Avg Vol 20D":   int(avg_vol),
            "Vol Ratio":     vl,
            "_vr":           vr,
            "Status":        get_status(pct_ab),
        })
        time.sleep(0.15)

    prog.empty(); status_text.empty()

    df_r = pd.DataFrame(results) if results else pd.DataFrame()
    if not df_r.empty:
        df_r = df_r[
            (df_r["% Above 52W"] >= min_pct) &
            (df_r["% Above 52W"] <= max_pct)
        ].sort_values("% Above 52W").reset_index(drop=True)

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")
    data_store.save("watchlist_df",   df_r)
    data_store.save("last_watchlist", ts)
    st.session_state["watchlist_data"] = df_r
    cached_df   = df_r
    cached_time = ts
    st.success(f"✅ Watchlist built: {len(df_r)} stocks at {ts}")

# ── Display ───────────────────────────────────────────────────────
# Use session_state first, then persistent store
df_r = st.session_state.get("watchlist_data") or cached_df

if df_r is None or (isinstance(df_r, pd.DataFrame) and df_r.empty):
    st.info("Set filters in the sidebar → click **🔄 FETCH WATCHLIST**")
    st.stop()

strong = (df_r["Status"] == "🟢 STRONG").sum()
mod    = (df_r["Status"] == "🟡 MODERATE").sum()
wtch   = (df_r["Status"] == "🟠 WATCH").sum()
vbk    = (df_r["_vr"] >= 1.5).sum()

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total",        len(df_r))
c2.metric("🟢 STRONG",   strong)
c3.metric("🟡 MODERATE", mod)
c4.metric("🟠 WATCH",    wtch)
c5.metric("🔥 Vol Brk",  vbk)

vb = df_r[df_r["_vr"] >= 1.5]
if not vb.empty:
    st.error("🔥 VOLUME BREAKOUT: " + " · ".join(f"{r['Symbol']} ({r['Vol Ratio']})" for _,r in vb.iterrows()))

st.divider()

def cs(v):
    if "STRONG"   in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "MODERATE" in str(v): return "background:#fff3cd;color:#856404;font-weight:700"
    if "WATCH"    in str(v): return "background:#ffe5d0;color:#7d4e00"
    return ""
def cv(v):
    if "🔥" in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "⚡" in str(v): return "background:#fff3cd;color:#856404"
    return ""

show = ["Name","Symbol","Sector","LTP","52W Low","% Above 52W","Mkt Cap (Cr)","Volume","Avg Vol 20D","Vol Ratio","Status"]
styled = (df_r[show].style
    .map(cs, subset=["Status"])
    .map(cv, subset=["Vol Ratio"])
    .format({"LTP":"₹{:,.2f}","52W Low":"₹{:,.2f}",
             "% Above 52W":"{:.2f}%","Mkt Cap (Cr)":"{:,.0f}",
             "Volume":"{:,}","Avg Vol 20D":"{:,}"}))
st.dataframe(styled, use_container_width=True, hide_index=True)
if cached_time:
    st.caption(f"Data from {cached_time} — refreshes only when you click 🔄 FETCH WATCHLIST")
