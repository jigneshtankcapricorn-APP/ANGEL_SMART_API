import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz

st.set_page_config(page_title="🧠 Signals", page_icon="🧠", layout="wide")

from utils.sidebar import render_sidebar, require_app_login
from utils import data_store

require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import calculate_supertrend_signals, compute_risk, compute_vol_ratio

st.title("🧠 SuperTrend Signals")
st.caption("SuperTrend(10,3) · ATR(10) · EMA 23 · Swing High · 🟢 BUY / ⚪ WATCH")

with st.sidebar:
    use_wl = st.checkbox("Use Watchlist stocks only", value=True)
    st.caption("🟢 BUY = Breakout + 5+ green days\n⚪ WATCH = GREEN, no breakout yet")

@st.cache_data(show_spinner=False)
def load_stocks():
    try:
        return pd.read_csv("data/stocks_full.csv")
    except FileNotFoundError:
        return pd.read_csv("data/stocks.csv")

stocks_df = load_stocks()

# ── Persistent data ───────────────────────────────────────────────
cached_df   = data_store.load("signals_df")
cached_meta = data_store.load("signals_meta")
cached_time = data_store.load("last_signals")

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_btn = st.button("🔄 RUN SIGNAL ANALYSIS", type="primary", use_container_width=True)
with col_info:
    if cached_time:
        st.info(f"📦 Last run: **{cached_time}** — data saved. Click to refresh.")

def get_universe():
    wl = st.session_state.get("watchlist_data")
    if wl is None or not isinstance(wl, pd.DataFrame) or wl.empty:
        wl = data_store.load("watchlist_df")
    if use_wl and wl is not None and not wl.empty:
        rows = []
        for _, r in wl.iterrows():
            rows.append({
                "name": r["Name"], "symbol": f"NSE:{r['Symbol']}",
                "sector": r["Sector"], "ref_ltp": r["LTP"],
                "w52_low": r["52W Low"],
                "market_cap_cr": r["Mkt Cap (Cr)"],
                "ref_volume": r["Volume"],
                "ref_avg_vol_20d": r["Avg Vol 20D"],
            })
        return pd.DataFrame(rows)
    return stocks_df.copy()

if run_btn:
    universe = get_universe()
    if universe.empty:
        st.warning("Build your **Watchlist** first, or uncheck 'Use Watchlist stocks only'.")
        st.stop()

    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()
    src = "Watchlist" if use_wl and (data_store.load("watchlist_df") is not None) else f"All {len(universe)} stocks"
    st.info(f"📊 Analysing {len(universe)} stocks from {src}…")

    results, buy_list, watch_list, high_vol = [], [], [], []
    prog = st.progress(0)
    lbl  = st.empty()

    for i, (_, row) in enumerate(universe.iterrows()):
        sym = str(row["symbol"])
        lbl.text(f"⏳ {row['name']} ({i+1}/{len(universe)})")
        prog.progress((i+1) / len(universe))

        token = get_token(instruments, sym)
        if not token: continue

        tsym = sym.replace("NSE:", "")
        ltp  = fetch_ltp(obj, "NSE", tsym, token) or row.get("ref_ltp", 0)
        ohlc = fetch_historical_ohlc(obj, token, "NSE", days=40)

        if not ohlc or len(ohlc) < 15:
            time.sleep(0.1); continue

        ohlc[-1]["close"] = ltp or ohlc[-1]["close"]
        sig = calculate_supertrend_signals(ohlc)

        if sig["supertrend_status"] != "🟢 GREEN":
            time.sleep(0.1); continue

        vol     = ohlc[-1]["volume"]
        avg_vol = sum(c["volume"] for c in ohlc[-21:-1]) / 20 if len(ohlc) >= 21 else row.get("ref_avg_vol_20d", 0)
        vr, vl  = compute_vol_ratio(vol, avg_vol)
        if vr >= 1.5: high_vol.append(f"{tsym}({vr:.1f}x)")

        risk   = compute_risk(ltp, sig["ema23"])
        signal = "🟢 BUY" if sig["is_breakout"] else "⚪ WATCH"
        (buy_list if signal == "🟢 BUY" else watch_list).append(tsym)

        w52l   = row.get("w52_low", 0)
        pct_ab = ((ltp - w52l) / w52l * 100) if w52l > 0 else 0

        results.append({
            "Symbol":       tsym,
            "Sector":       row.get("sector", "Unknown"),
            "LTP":          round(ltp, 2),
            "% Above 52W":  round(pct_ab, 2),
            "Days Green":   sig["days_green"],
            "Flat?":        "✅" if sig["is_flat"] else "❌",
            "Swing High":   sig["swing_high"] or "—",
            "SH Date":      sig["swing_high_date"] or "—",
            "Breakout?":    "✅" if sig["is_breakout"] else "❌",
            "23-EMA":       sig["ema23"] or "—",
            "SL 5%":        risk["sl_5pct"],
            "Rec SL":       risk["recommended_sl"],
            "Risk %":       risk["risk_ema_pct"],
            "Vol Ratio":    vl,
            "_vr":          vr,
            "Risk Status":  risk["risk_status"],
            "SIGNAL":       signal,
        })
        time.sleep(0.15)

    prog.empty(); lbl.empty()

    df_out = pd.DataFrame(results) if results else pd.DataFrame()
    meta   = {"buy": buy_list, "watch": watch_list, "high_vol": high_vol, "total": len(universe)}
    ist    = pytz.timezone("Asia/Kolkata")
    ts     = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    data_store.save("signals_df",   df_out)
    data_store.save("signals_meta", meta)
    data_store.save("last_signals", ts)
    st.session_state["signals_data"] = df_out

    cached_df   = df_out
    cached_meta = meta
    cached_time = ts
    st.success(f"✅ Analysis done at {ts}")

# ── Display ───────────────────────────────────────────────────────
df = st.session_state.get("signals_data")
if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    df = cached_df
meta = cached_meta or {}

if df is None or (isinstance(df, pd.DataFrame) and df.empty):
    if not run_btn:
        st.info("Build **Watchlist** first → then click **🔄 RUN SIGNAL ANALYSIS**")
    else:
        st.warning("No GREEN SuperTrend stocks found.")
    st.stop()

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Analysed",    meta.get("total", "—"))
c2.metric("🟢 GREEN",    len(df))
c3.metric("🟢 BUY",      len(meta.get("buy",[])))
c4.metric("⚪ WATCH",    len(meta.get("watch",[])))
c5.metric("🔥 High Vol", len(meta.get("high_vol",[])))

if meta.get("buy"):
    st.success("🟢 BUY SIGNALS: " + " · ".join(meta["buy"]))
if meta.get("high_vol"):
    st.error("🔥 HIGH VOLUME: " + " · ".join(meta["high_vol"]))

st.divider()

f1, f2 = st.columns(2)
fs = f1.multiselect("Filter Signal",  ["🟢 BUY","⚪ WATCH"],["🟢 BUY","⚪ WATCH"])
fr = f2.multiselect("Filter Risk",    ["🟢 LOW RISK","🟡 MODERATE","⚠️ HIGH RISK"],
                                       ["🟢 LOW RISK","🟡 MODERATE","⚠️ HIGH RISK"])

df_show = df[df["SIGNAL"].isin(fs) & df["Risk Status"].isin(fr)].copy()

def ss(v):
    if v == "🟢 BUY":  return "background:#28a745;color:white;font-weight:700"
    if v == "⚪ WATCH": return "background:#ffc107;color:black;font-weight:700"
    return ""
def sr(v):
    if "LOW"      in str(v): return "background:#d4edda;color:#155724"
    if "MODERATE" in str(v): return "background:#fff3cd;color:#856404"
    if "HIGH"     in str(v): return "background:#f8d7da;color:#721c24"
    return ""
def sv(v):
    if "🔥" in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "⚡" in str(v): return "background:#fff3cd;color:#856404"
    return ""

show = ["Symbol","Sector","LTP","% Above 52W","Days Green","Flat?",
        "Swing High","SH Date","Breakout?","23-EMA",
        "SL 5%","Rec SL","Risk %","Vol Ratio","Risk Status","SIGNAL"]
df_d = df_show[[c for c in show if c in df_show.columns]]

styled = (df_d.style
    .map(ss, subset=["SIGNAL"])
    .map(sr, subset=["Risk Status"])
    .map(sv, subset=["Vol Ratio"])
    .format({"LTP":"₹{:,.2f}","% Above 52W":"{:.2f}%",
             "SL 5%":"₹{:,.2f}","Rec SL":"₹{:,.2f}","Risk %":"{:.2f}%"}, na_rep="—"))

st.markdown(f"### 📋 {len(df_d)} stocks")
st.dataframe(styled, use_container_width=True, hide_index=True)
if cached_time:
    st.caption(f"Data from {cached_time} — refreshes only when you click 🔄 RUN SIGNAL ANALYSIS")
