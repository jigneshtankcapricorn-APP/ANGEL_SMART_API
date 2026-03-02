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
st.caption("Live NSE Sector Indices · 🟢 BULL · 🔴 BEAR · ⚪ NEUTRAL")

cached_df   = data_store.load("sector_df")
cached_time = data_store.load("last_sector")

col_fetch, col_info = st.columns([1, 3])
with col_fetch:
    fetch_btn = st.button("🔄 FETCH SECTOR DATA", type="primary", use_container_width=True)
with col_info:
    if cached_time:
        st.info(f"📦 Last fetched: **{cached_time}** — data saved. Click Fetch to refresh.")
    else:
        st.warning("No data yet — click **🔄 FETCH SECTOR DATA**")

if fetch_btn:
    obj = st.session_state.angel_obj
    with st.spinner("📡 Fetching live NSE sector index data…"):
        rows = fetch_sector_data(obj)

    if rows:
        df_new = pd.DataFrame(rows).sort_values("_d", ascending=False).drop(columns=["_d"])
        ist = pytz.timezone("Asia/Kolkata")
        ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")
        data_store.save("sector_df", df_new)
        data_store.save("last_sector", ts)
        cached_df   = df_new
        cached_time = ts
        st.success(f"✅ Fetched {len(df_new)} sector indices at {ts}")
    else:
        st.error("❌ Could not fetch live sector indices. Trying stock-based fallback…")
        sig_data = st.session_state.get("signals_data") or data_store.load("signals_df")
        wl_data  = st.session_state.get("watchlist_data") or data_store.load("watchlist_df")
        df_src = None
        if sig_data is not None and not sig_data.empty and "Sector" in sig_data.columns:
            df_src = sig_data[["Sector","% Above 52W"]].rename(columns={"% Above 52W":"proxy"})
        elif wl_data is not None and not wl_data.empty and "Sector" in wl_data.columns:
            df_src = wl_data[["Sector","% Above 52W"]].rename(columns={"% Above 52W":"proxy"})
        if df_src is not None:
            fb_rows = []
            for sec, grp in df_src.groupby("Sector"):
                sec = str(sec).strip()
                if not sec or sec in ("nan","Unknown","Others",""): continue
                avg = grp["proxy"].mean()
                d, w, m = avg*0.15, avg*0.4, avg
                fb_rows.append({"Sector":sec,"Stocks":len(grp),"Daily %":round(d,2),
                                 "Weekly %":round(w,2),"Monthly %":round(m,2),
                                 "Trend":sector_trend(d,w,m),"_d":d,"Source":"stock-estimate"})
            if fb_rows:
                df_new = pd.DataFrame(fb_rows).sort_values("_d",ascending=False).drop(columns=["_d"])
                data_store.save("sector_df", df_new)
                data_store.save("last_sector", "stock-based estimate")
                cached_df = df_new
                st.warning("⚠️ Showing stock-based estimate — not real sector index values.")

if cached_df is None or cached_df.empty:
    st.stop()

df_s = cached_df.copy()
bull = df_s["Trend"].str.contains("BULL").sum()
bear = df_s["Trend"].str.contains("BEAR").sum()

st.divider()
c1,c2,c3,c4 = st.columns(4)
c1.metric("Total Sectors", len(df_s))
c2.metric("🟢 Bullish",    int(bull))
c3.metric("🔴 Bearish",    int(bear))
c4.metric("⚪ Neutral",    int(len(df_s)-bull-bear))
st.divider()

def _ts(v):
    if "BULL"    in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "BEAR"    in str(v): return "background:#f8d7da;color:#721c24;font-weight:700"
    if "NEUTRAL" in str(v): return "background:#fff3cd;color:#856404"
    return ""
def _ps(v):
    try: return "background:#d4edda;color:#155724" if float(v)>0 else "background:#f8d7da;color:#721c24"
    except: return ""

show_cols = [c for c in ["Sector","LTP","Daily %","Weekly %","Monthly %","Trend","Source","Stocks"] if c in df_s.columns]
fmt = {}
for col in ["Daily %","Weekly %","Monthly %"]:
    if col in df_s.columns: fmt[col] = "{:+.2f}%"
if "LTP" in df_s.columns: fmt["LTP"] = "₹{:,.2f}"

styled = df_s[show_cols].style.map(_ts, subset=["Trend"])
for col in ["Daily %","Weekly %","Monthly %"]:
    if col in show_cols: styled = styled.map(_ps, subset=[col])
styled = styled.format(fmt, na_rep="—")

st.dataframe(styled, use_container_width=True, hide_index=True)
st.divider()

cb, cbr = st.columns(2)
with cb:
    st.markdown("#### 🟢 Bullish Sectors")
    for s in df_s[df_s["Trend"].str.contains("BULL")]["Sector"].tolist():
        st.success(s)
with cbr:
    st.markdown("#### 🔴 Bearish Sectors")
    for s in df_s[df_s["Trend"].str.contains("BEAR")]["Sector"].tolist():
        st.error(s)

src_note = "✅ Live NSE Sector Index data via Angel One API" if "Source" in df_s.columns and (df_s["Source"]=="live").all() else "⚠️ Estimated from stock data. Live index fetch failed."
st.caption(src_note)
