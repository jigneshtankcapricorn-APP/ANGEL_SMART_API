import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz
import os

st.set_page_config(page_title="📌 Monitor", page_icon="📌", layout="wide")

from utils.sidebar import render_sidebar, require_app_login, check_session_alive
from utils import data_store

require_app_login()
render_sidebar()

# ── Monitor CSV path (permanent storage) ─────────────────────────
MONITOR_CSV = "data/monitor_stocks.csv"

# ── CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.page-title{font-size:1.8rem;font-weight:700;color:#7B2FBE;margin-bottom:2px;}
.sub-caption{color:#666;font-size:.88rem;margin-bottom:16px;}
.saved-banner{background:#ede7f6;border:1px solid #ce93d8;border-radius:8px;
              padding:10px 16px;color:#4a148c;font-size:.9rem;margin-bottom:12px;}
.warn-banner{background:#fff3cd;border:1px solid #ffc107;border-radius:8px;
             padding:10px 16px;color:#856404;font-size:.9rem;margin-bottom:12px;}
.info-banner{background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;
             padding:10px 16px;color:#0d47a1;font-size:.9rem;margin-bottom:12px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">📌 Monitor — My Watchlist</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-caption">Stocks saved from Signals page · '
    'Tracks Swing High, Entry Price & Current Price · '
    'Stays permanent until you remove a stock</div>',
    unsafe_allow_html=True
)

# ── Load / Save Monitor CSV ───────────────────────────────────────
def load_monitor() -> pd.DataFrame:
    if os.path.exists(MONITOR_CSV):
        try:
            df = pd.read_csv(MONITOR_CSV)
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def save_monitor(df: pd.DataFrame):
    os.makedirs("data", exist_ok=True)
    df.to_csv(MONITOR_CSV, index=False)

monitor_df = load_monitor()

# ── If not connected, still show saved data (read-only) ──────────
connected = st.session_state.get("connected", False)

# ─────────────────────────────────────────────────────────────────
# EMPTY STATE
# ─────────────────────────────────────────────────────────────────
if monitor_df.empty:
    st.markdown(
        '<div class="warn-banner">📭 No stocks saved yet. '
        'Go to <b>🧠 Signals</b> page → select stocks with ☑️ checkbox → '
        'click <b>📌 Save to Monitor</b></div>',
        unsafe_allow_html=True
    )
    st.stop()

# ─────────────────────────────────────────────────────────────────
# REFRESH LIVE PRICES BUTTON
# ─────────────────────────────────────────────────────────────────
col_refresh, col_clear, col_info = st.columns([1.5, 1.2, 3])

with col_refresh:
    refresh_btn = st.button(
        "🔄 Refresh Current Prices",
        type="primary",
        use_container_width=True,
        disabled=not connected
    )
with col_clear:
    clear_all_btn = st.button(
        "🗑️ Clear All",
        use_container_width=True
    )
with col_info:
    last_refresh = st.session_state.get("monitor_last_refresh", None)
    if not connected:
        st.markdown(
            '<div class="warn-banner">⚠️ Connect to Angel One in sidebar to refresh live prices</div>',
            unsafe_allow_html=True
        )
    elif last_refresh:
        st.markdown(
            f'<div class="saved-banner">🕐 Last refreshed: <b>{last_refresh}</b></div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="info-banner">💡 Click 🔄 Refresh to fetch current prices from Angel One</div>',
            unsafe_allow_html=True
        )

if clear_all_btn:
    save_monitor(pd.DataFrame())
    st.session_state.pop("monitor_last_refresh", None)
    st.success("✅ All monitor stocks cleared.")
    st.rerun()

# ─────────────────────────────────────────────────────────────────
# REFRESH LIVE PRICES
# ─────────────────────────────────────────────────────────────────
if refresh_btn and connected:
    if not check_session_alive():
        st.error("❌ Angel One session expired. Please Reconnect from sidebar.")
        st.stop()

    from utils.angel_connect import load_instrument_master, get_token, fetch_ltp
    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    prog     = st.progress(0)
    lbl      = st.empty()
    symbols  = monitor_df["Symbol"].tolist()
    new_ltps = {}

    for i, sym in enumerate(symbols):
        prog.progress((i + 1) / len(symbols))
        lbl.markdown(f"Fetching **{sym}** ({i+1}/{len(symbols)})…")
        try:
            token = get_token(instruments, sym)
            if token:
                ltp = fetch_ltp(obj, "NSE", sym, token)
                if ltp and ltp > 0:
                    new_ltps[sym] = round(ltp, 2)
        except Exception:
            pass
        time.sleep(0.12)

    prog.empty()
    lbl.empty()

    # Update current price in dataframe
    for sym, ltp in new_ltps.items():
        monitor_df.loc[monitor_df["Symbol"] == sym, "Current_Price"] = ltp

    save_monitor(monitor_df)

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")
    st.session_state["monitor_last_refresh"] = ts

    st.success(f"✅ Updated prices for {len(new_ltps)} of {len(symbols)} stocks.")
    st.rerun()

# ─────────────────────────────────────────────────────────────────
# SUMMARY METRICS
# ─────────────────────────────────────────────────────────────────
st.divider()

total  = len(monitor_df)
buy_ct = int((monitor_df.get("SIGNAL", pd.Series()) == "🟢 BUY").sum())  if "SIGNAL" in monitor_df.columns else 0
wtch_ct= int((monitor_df.get("SIGNAL", pd.Series()) == "⚪ WATCH").sum()) if "SIGNAL" in monitor_df.columns else 0

# Compute % change from entry → current
if "Entry_Price" in monitor_df.columns and "Current_Price" in monitor_df.columns:
    monitor_df["% Change"] = monitor_df.apply(
        lambda r: round(
            (r["Current_Price"] - r["Entry_Price"]) / r["Entry_Price"] * 100, 2
        ) if r["Entry_Price"] > 0 and r["Current_Price"] > 0 else None,
        axis=1
    )
    gainers = int((monitor_df["% Change"] > 0).sum())
    losers  = int((monitor_df["% Change"] < 0).sum())
else:
    gainers, losers = 0, 0

# Days held
if "Added_On" in monitor_df.columns:
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    def days_held(added_on_str):
        try:
            added = datetime.strptime(str(added_on_str), "%d %b %Y %H:%M IST")
            return (now.replace(tzinfo=None) - added).days
        except Exception:
            return "—"
    monitor_df["Days Held"] = monitor_df["Added_On"].apply(days_held)
else:
    monitor_df["Days Held"] = "—"

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("📌 Monitoring",   total)
m2.metric("🟢 BUY signals",  buy_ct)
m3.metric("⚪ WATCH",        wtch_ct)
m4.metric("📈 Gainers",      gainers)
m5.metric("📉 Losers",       losers)

st.divider()

# ─────────────────────────────────────────────────────────────────
# DISPLAY TABLE + REMOVE BUTTONS
# ─────────────────────────────────────────────────────────────────

# Columns to show (only those that exist)
SHOW_COLS = [
    "Symbol", "Sector", "SIGNAL",
    "Entry_Price", "Current_Price", "% Change", "Days Held",
    "Days_Green", "Flat", "Swing_High", "SH_Date",
    "Breakout", "EMA23", "SL_5pct", "Rec_SL", "Risk_pct",
    "Risk_Status", "Vol_Ratio", "Added_On"
]
RENAME = {
    "Entry_Price":  "Entry ₹",
    "Current_Price":"Current ₹",
    "Days_Green":   "Days Green",
    "Swing_High":   "Swing High",
    "SH_Date":      "SH Date",
    "EMA23":        "23-EMA",
    "SL_5pct":      "SL 5%",
    "Rec_SL":       "Rec SL",
    "Risk_pct":     "Risk %",
    "Risk_Status":  "Risk Status",
    "Vol_Ratio":    "Vol Ratio",
    "Added_On":     "Saved On",
    "Flat":         "Flat?",
    "Breakout":     "Breakout?",
}

show_cols = [c for c in SHOW_COLS if c in monitor_df.columns]
df_display = monitor_df[show_cols].rename(columns=RENAME).copy()

# Styling functions
def ss(v):
    if v == "🟢 BUY":   return "background:#28a745;color:white;font-weight:700"
    if v == "⚪ WATCH":  return "background:#ffc107;color:black;font-weight:700"
    return ""

def sr(v):
    if "LOW"      in str(v): return "background:#d4edda;color:#155724"
    if "MODERATE" in str(v): return "background:#fff3cd;color:#856404"
    if "HIGH"     in str(v): return "background:#f8d7da;color:#721c24"
    return ""

def sc(v):
    try:
        f = float(str(v).replace("%",""))
        if f > 0:  return "color:#155724;font-weight:600"
        if f < 0:  return "color:#721c24;font-weight:600"
    except: pass
    return ""

def sv(v):
    if "🔥" in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "⚡" in str(v): return "background:#fff3cd;color:#856404"
    return ""

fmt_map = {}
if "Entry ₹"   in df_display.columns: fmt_map["Entry ₹"]   = "₹{:,.2f}"
if "Current ₹" in df_display.columns: fmt_map["Current ₹"] = "₹{:,.2f}"
if "% Change"  in df_display.columns: fmt_map["% Change"]  = "{:.2f}%"
if "SL 5%"     in df_display.columns: fmt_map["SL 5%"]     = "₹{:,.2f}"
if "Rec SL"    in df_display.columns: fmt_map["Rec SL"]    = "₹{:,.2f}"
if "Risk %"    in df_display.columns: fmt_map["Risk %"]    = "{:.2f}%"
if "23-EMA"    in df_display.columns: fmt_map["23-EMA"]    = "₹{:,.2f}"
if "Swing High"in df_display.columns: fmt_map["Swing High"]= "₹{:,.2f}"

try:
    styled = df_display.style
    if "SIGNAL"      in df_display.columns: styled = styled.map(ss, subset=["SIGNAL"])
    if "Risk Status" in df_display.columns: styled = styled.map(sr, subset=["Risk Status"])
    if "% Change"    in df_display.columns: styled = styled.map(sc, subset=["% Change"])
    if "Vol Ratio"   in df_display.columns: styled = styled.map(sv, subset=["Vol Ratio"])
    if fmt_map:
        styled = styled.format(fmt_map, na_rep="—")
    st.dataframe(styled, use_container_width=True, hide_index=True)
except Exception:
    st.dataframe(df_display, use_container_width=True, hide_index=True)

st.divider()

# ─────────────────────────────────────────────────────────────────
# REMOVE INDIVIDUAL STOCKS
# ─────────────────────────────────────────────────────────────────
st.markdown("### 🗑️ Remove a Stock from Monitor")
st.caption("Select the stock you want to stop monitoring, then click Remove.")

symbols_list = monitor_df["Symbol"].tolist()
col_sel, col_rm = st.columns([2, 1])
with col_sel:
    remove_sym = st.selectbox(
        "Select stock to remove",
        options=symbols_list,
        index=0,
        label_visibility="collapsed"
    )
with col_rm:
    if st.button(f"🗑️ Remove {remove_sym}", type="secondary", use_container_width=True):
        monitor_df = monitor_df[monitor_df["Symbol"] != remove_sym].reset_index(drop=True)
        save_monitor(monitor_df)
        st.success(f"✅ {remove_sym} removed from Monitor.")
        st.rerun()

st.caption(f"📅 {total} stock(s) currently monitored · Saves to `data/monitor_stocks.csv` permanently")
