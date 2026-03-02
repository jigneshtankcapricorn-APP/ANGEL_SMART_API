import streamlit as st
import pandas as pd
from datetime import datetime
import pytz

st.set_page_config(page_title="🏭 Sector Trends", page_icon="🏭", layout="wide")

from utils.sidebar import render_sidebar, require_app_login
from utils import data_store

require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.sector_indices import fetch_sector_data
from utils.indicators import sector_trend

st.title("🏭 Sector Trends")
st.caption("Live NSE Sector Indices + Stock-based sector data from your CSV · 🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL")

# ── Load CSV sector data ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv("data/stocks_full.csv")

stocks_df = load_stocks()

# ── Persistent data ───────────────────────────────────────────────
cached_df   = data_store.load("sector_df")
cached_time = data_store.load("last_sector")

# ── Source selector ───────────────────────────────────────────────
source_mode = st.radio(
    "Data Source",
    ["🔴 Live NSE Sector Indices (Angel One)", "📊 From Watchlist/Signals results", "📋 All sectors from CSV list"],
    horizontal=True,
    help="Live = real index prices. CSV = all 836 sectors from your uploaded SHARE.csv"
)

col_fetch, col_info = st.columns([1, 3])
with col_fetch:
    fetch_btn = st.button("🔄 FETCH / BUILD", type="primary", use_container_width=True)
with col_info:
    if cached_time:
        st.info(f"📦 Last fetched: **{cached_time}** · Click 🔄 to refresh manually")
    else:
        st.warning("No data yet — click **🔄 FETCH / BUILD**")

# ── Fetch / Build ─────────────────────────────────────────────────
if fetch_btn:
    ist = pytz.timezone("Asia/Kolkata")
    rows = []

    # ── Mode 1: Live NSE Sector Indices ───────────────────────────
    if "Live NSE" in source_mode:
        obj = st.session_state.angel_obj
        with st.spinner("📡 Fetching live NSE sector index data from Angel One…"):
            rows = fetch_sector_data(obj)

        if not rows:
            st.warning("⚠️ Live sector indices not available. Switching to CSV-based data automatically.")
            source_mode = "📋 All sectors from CSV list"

    # ── Mode 2: From Watchlist / Signals ──────────────────────────
    if "Watchlist/Signals" in source_mode:
        sig_df = st.session_state.get("signals_data")
        if sig_df is None or not isinstance(sig_df, pd.DataFrame) or sig_df.empty:
            sig_df = data_store.load("signals_df")
        wl_df = st.session_state.get("watchlist_data")
        if wl_df is None or not isinstance(wl_df, pd.DataFrame) or wl_df.empty:
            wl_df = data_store.load("watchlist_df")

        df_src = None
        src_lbl = ""
        if sig_df is not None and isinstance(sig_df, pd.DataFrame) and not sig_df.empty and "Sector" in sig_df.columns:
            df_src  = sig_df[["Sector","% Above 52W"]].rename(columns={"% Above 52W":"proxy"})
            src_lbl = "Signals"
        elif wl_df is not None and isinstance(wl_df, pd.DataFrame) and not wl_df.empty and "Sector" in wl_df.columns:
            df_src  = wl_df[["Sector","% Above 52W"]].rename(columns={"% Above 52W":"proxy"})
            src_lbl = "Watchlist"

        if df_src is not None and not df_src.empty:
            for sec, grp in df_src.groupby("Sector"):
                sec = str(sec).strip()
                if not sec or sec in ("nan","Unknown","","-","—"): continue
                avg = grp["proxy"].mean()
                d, w, m = avg*0.15, avg*0.4, avg
                rows.append({
                    "Sector":    sec, "Stocks": len(grp),
                    "Daily %":   round(d,2), "Weekly %":  round(w,2), "Monthly %": round(m,2),
                    "Trend":     sector_trend(d,w,m), "_d": d, "Source": src_lbl
                })
        else:
            st.warning("No Watchlist or Signals data found. Run Watchlist first, then come back.")

    # ── Mode 3: All sectors from CSV ──────────────────────────────
    if "CSV list" in source_mode:
        df_csv = stocks_df[
            stocks_df["sector"].notna() &
            (stocks_df["sector"] != "Unknown") &
            (stocks_df["sector"].str.strip() != "")
        ].copy()

        for sec, grp in df_csv.groupby("sector"):
            sec = str(sec).strip()
            if not sec or sec in ("nan","Unknown","","-","—"): continue
            avg_mcap = grp["market_cap_cr"].mean() if "market_cap_cr" in grp.columns else 0
            rows.append({
                "Sector":    sec,
                "Stocks":    len(grp),
                "Avg Mkt Cap (Cr)": round(avg_mcap, 0) if avg_mcap > 0 else None,
                "Daily %":   0.0,
                "Weekly %":  0.0,
                "Monthly %": 0.0,
                "Trend":     "⚪ NEUTRAL",
                "_d":        0.0,
                "Source":    "CSV reference"
            })
        st.info(
            f"📋 Showing all **{len(rows)} sectors** from your SHARE.csv. "
            f"Daily/Weekly/Monthly % will be 0 — use Live or Watchlist/Signals mode for real price trends."
        )

    if rows:
        df_new = pd.DataFrame(rows).sort_values("_d", ascending=False).drop(columns=["_d"])
        ts = datetime.now(ist).strftime("%d %b %Y %H:%M IST") + f" ({source_mode.split('(')[0].strip()})"
        data_store.save("sector_df",   df_new)
        data_store.save("last_sector", ts)
        cached_df   = df_new
        cached_time = ts
        st.success(f"✅ Built {len(df_new)} sectors at {ts}")

# ── Display ───────────────────────────────────────────────────────
if cached_df is None or not isinstance(cached_df, pd.DataFrame) or cached_df.empty:
    st.stop()

df_s = cached_df.copy()

# Display search/filter
search_sec = st.text_input("🔍 Search sector name", placeholder="e.g. Pharma, IT, Finance…")
if search_sec:
    df_s = df_s[df_s["Sector"].str.contains(search_sec, case=False, na=False)]

bull = int(df_s["Trend"].str.contains("BULL").sum())
bear = int(df_s["Trend"].str.contains("BEAR").sum())
neut = len(df_s) - bull - bear

st.divider()
c1,c2,c3,c4 = st.columns(4)
c1.metric("Total Sectors", len(df_s))
c2.metric("🟢 Bullish",    bull)
c3.metric("🔴 Bearish",    bear)
c4.metric("⚪ Neutral",    neut)
st.divider()

def _ts(v):
    if "BULL"    in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "BEAR"    in str(v): return "background:#f8d7da;color:#721c24;font-weight:700"
    if "NEUTRAL" in str(v): return "background:#fff3cd;color:#856404"
    return ""
def _ps(v):
    try: return "background:#d4edda;color:#155724" if float(v)>0 else ("background:#f8d7da;color:#721c24" if float(v)<0 else "")
    except: return ""

show_cols = [c for c in ["Sector","Stocks","Avg Mkt Cap (Cr)","LTP","Daily %","Weekly %","Monthly %","Trend","Source"] if c in df_s.columns]
fmt = {}
for col in ["Daily %","Weekly %","Monthly %"]:
    if col in df_s.columns: fmt[col] = "{:+.2f}%"
if "LTP"           in df_s.columns: fmt["LTP"]           = "₹{:,.2f}"
if "Avg Mkt Cap (Cr)" in df_s.columns: fmt["Avg Mkt Cap (Cr)"] = "₹{:,.0f}"

styled = df_s[show_cols].style.map(_ts, subset=["Trend"])
for col in ["Daily %","Weekly %","Monthly %"]:
    if col in show_cols: styled = styled.map(_ps, subset=[col])
styled = styled.format(fmt, na_rep="—")

st.dataframe(styled, use_container_width=True, hide_index=True, height=600)
st.divider()

# ── Bull / Bear panels ────────────────────────────────────────────
if bull > 0 or bear > 0:
    cb, cbr = st.columns(2)
    with cb:
        st.markdown("#### 🟢 Bullish Sectors")
        bulls = df_s[df_s["Trend"].str.contains("BULL")]["Sector"].tolist()
        for s in bulls[:20]:
            st.success(s)
        if len(bulls) > 20: st.caption(f"+{len(bulls)-20} more…")
    with cbr:
        st.markdown("#### 🔴 Bearish Sectors")
        bears = df_s[df_s["Trend"].str.contains("BEAR")]["Sector"].tolist()
        for s in bears[:20]:
            st.error(s)
        if len(bears) > 20: st.caption(f"+{len(bears)-20} more…")

if cached_time:
    st.caption(f"📅 Data from: **{cached_time}** · No auto-refresh · Click 🔄 to update manually")
