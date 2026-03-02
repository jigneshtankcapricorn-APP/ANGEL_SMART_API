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

from utils.angel_connect import (
    load_instrument_master, get_token,
    fetch_historical_ohlc, fetch_ltp, fetch_live_52w
)
from utils.indicators import compute_vol_ratio

# ── Load stock universe ───────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv("data/stocks_full.csv")  # name, symbol, market_cap_cr

stocks_df = load_stocks()
TOTAL     = len(stocks_df)

# ─────────────────────────────────────────────────────────────────
# PERSIST FILTER SETTINGS IN SESSION STATE
# So they never reset when you navigate away and come back
# ─────────────────────────────────────────────────────────────────
def ss_init(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

ss_init("wl_min_pct",    1.0)
ss_init("wl_max_pct",    15.0)
ss_init("wl_min_mcap",   0.0)
ss_init("wl_mcap_apply", False)
ss_init("wl_batch_size", 200)
ss_init("wl_batch_start",1)
ss_init("wl_timeout",    0.12)

# ─────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.page-title{font-size:1.8rem;font-weight:700;color:#1A73E8;margin-bottom:2px;}
.sub-caption{color:#666;font-size:.88rem;margin-bottom:16px;}
.saved-banner{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;
              padding:10px 16px;color:#1b5e20;font-size:.9rem;margin-bottom:12px;}
.warn-banner{background:#fff3cd;border:1px solid #ffc107;border-radius:8px;
             padding:10px 16px;color:#856404;font-size:.9rem;margin-bottom:12px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">📋 Watchlist</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-caption">Universe: <b>{TOTAL:,} stocks</b> · '
    f'All prices fetched live from Angel One · '
    f'Filters &amp; batch settings remembered across pages</div>',
    unsafe_allow_html=True
)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR — filters saved to session_state so they persist
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Scan Filters")
    st.divider()

    # ── 52W Low filter ────────────────────────────────────────────
    st.markdown("**📊 52W Low Range**")
    min_pct = st.number_input(
        "Min % Above 52W Low", 0.0, 500.0,
        value=st.session_state.wl_min_pct, step=0.5,
        help="Stock must be AT LEAST this % above its 52-week low"
    )
    max_pct = st.number_input(
        "Max % Above 52W Low", 0.0, 500.0,
        value=st.session_state.wl_max_pct, step=0.5,
        help="Stock must be NO MORE than this % above its 52-week low"
    )
    st.session_state.wl_min_pct = min_pct
    st.session_state.wl_max_pct = max_pct

    st.divider()

    # ── Market Cap filter ─────────────────────────────────────────
    st.markdown("**💰 Market Cap Filter**")
    mcap_apply = st.checkbox(
        "Enable Market Cap Filter",
        value=st.session_state.wl_mcap_apply,
        help="Note: Market cap known for ~499 stocks. Others will pass through."
    )
    st.session_state.wl_mcap_apply = mcap_apply

    if mcap_apply:
        min_mcap = st.number_input(
            "Min Market Cap (Cr ₹)", 0.0, 1000000.0,
            value=st.session_state.wl_min_mcap, step=100.0,
            help="Only show stocks with market cap ≥ this value (Crores)"
        )
        st.session_state.wl_min_mcap = min_mcap

        mcap_cat = st.selectbox(
            "Quick Select",
            ["Custom", "Small Cap (< ₹5,000 Cr)", "Mid Cap (₹5,000–₹20,000 Cr)",
             "Large Cap (> ₹20,000 Cr)", "All sizes"],
            index=0,
            help="Shortcut to set market cap range"
        )
        if mcap_cat == "Small Cap (< ₹5,000 Cr)":
            min_mcap = 0.0
            st.session_state.wl_min_mcap = 0.0
        elif mcap_cat == "Mid Cap (₹5,000–₹20,000 Cr)":
            min_mcap = 5000.0
            st.session_state.wl_min_mcap = 5000.0
        elif mcap_cat == "Large Cap (> ₹20,000 Cr)":
            min_mcap = 20000.0
            st.session_state.wl_min_mcap = 20000.0
        elif mcap_cat == "All sizes":
            min_mcap = 0.0
            st.session_state.wl_min_mcap = 0.0

        st.caption("⚠️ Market cap data available for ~499 stocks only. Remaining stocks will not be filtered by market cap.")
    else:
        min_mcap = 0.0

    st.divider()

    # ── Batch settings ────────────────────────────────────────────
    st.markdown("### 📦 Batch Settings")

    batch_size = st.select_slider(
        "Batch Size (stocks per run)",
        options=[50, 100, 200, 300, 500, 1000, 2242],
        value=st.session_state.wl_batch_size,
        help="200 recommended. Full scan (2242) takes ~4-5 hours."
    )
    st.session_state.wl_batch_size = batch_size

    batch_start = st.number_input(
        "Start from stock #", min_value=1, max_value=TOTAL,
        value=st.session_state.wl_batch_start, step=1,
        help="Set this to resume after a timeout"
    )
    st.session_state.wl_batch_start = batch_start

    timeout_per = st.number_input(
        "Delay per stock (sec)", min_value=0.05, max_value=2.0,
        value=st.session_state.wl_timeout, step=0.01,
        help="0.10–0.12 recommended"
    )
    st.session_state.wl_timeout = timeout_per

    st.divider()
    st.caption("🟢 STRONG ≤12% · 🟡 MOD 12-15% · 🟠 WATCH >15%")

# ─────────────────────────────────────────────────────────────────
# ACTION BUTTONS + SAVED DATA BANNER
# ─────────────────────────────────────────────────────────────────
cached_df   = data_store.load("watchlist_df")
cached_time = data_store.load("last_watchlist")

col_btn, col_clr, col_info = st.columns([1.2, 1, 3])
with col_btn:
    run_btn = st.button("🔄 FETCH WATCHLIST", type="primary", use_container_width=True)
with col_clr:
    clear_btn = st.button("🗑️ Clear Data", use_container_width=True)
with col_info:
    if cached_time:
        st.markdown(
            f'<div class="saved-banner">📦 Saved data from <b>{cached_time}</b> '
            f'— no auto-refresh. Click 🔄 to update manually.</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="warn-banner">No data yet — set your filters and click 🔄 FETCH WATCHLIST</div>',
            unsafe_allow_html=True
        )

if clear_btn:
    data_store.clear("watchlist_df")
    data_store.clear("last_watchlist")
    st.session_state.pop("watchlist_data", None)
    st.rerun()

def get_status(pct):
    if pct <= 12: return "🟢 STRONG"
    if pct <= 15: return "🟡 MODERATE"
    return "🟠 WATCH"

# ─────────────────────────────────────────────────────────────────
# FETCH LIVE DATA
# ─────────────────────────────────────────────────────────────────
if run_btn:
    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    # Apply market cap pre-filter where data available
    df_work = stocks_df.copy()
    if mcap_apply and min_mcap > 0:
        known   = df_work[df_work["market_cap_cr"] > 0]
        unknown = df_work[df_work["market_cap_cr"] == 0]
        known   = known[known["market_cap_cr"] >= min_mcap]
        df_work = pd.concat([known, unknown], ignore_index=True)

    # Batch slice
    start_idx = batch_start - 1
    end_idx   = min(start_idx + batch_size, len(df_work))
    batch_df  = df_work.iloc[start_idx:end_idx].reset_index(drop=True)

    st.divider()
    prog_col, stat_col = st.columns([3, 1])
    with prog_col:
        prog_bar  = st.progress(0)
        prog_text = st.empty()
    with stat_col:
        stat_box = st.empty()

    results    = []
    skipped    = 0
    errors     = 0
    scan_start = time.time()

    for i, (_, row) in enumerate(batch_df.iterrows()):
        sym  = str(row["symbol"]).strip()
        name = str(row["name"]).strip()
        pct_done = (i + 1) / len(batch_df)

        elapsed = time.time() - scan_start
        eta_sec = (elapsed / (i+1)) * (len(batch_df)-i-1) if i > 0 else 0
        eta_str = f"{int(eta_sec//60)}m {int(eta_sec%60)}s" if eta_sec > 60 else f"{int(eta_sec)}s"

        prog_bar.progress(pct_done)
        prog_text.markdown(
            f"**[{i+1}/{len(batch_df)}]** `{sym}` — {name}  \n"
            f"⏱ {int(elapsed//60)}m{int(elapsed%60)}s elapsed · ETA: {eta_str} · ✅ {len(results)} found"
        )
        stat_box.metric("✅ Found", len(results))

        token = get_token(instruments, sym)
        if not token:
            skipped += 1
            continue

        try:
            ltp = fetch_ltp(obj, "NSE", sym, token)
        except Exception:
            errors += 1
            time.sleep(timeout_per)
            continue

        if not ltp or ltp == 0:
            skipped += 1
            time.sleep(0.05)
            continue

        try:
            live52 = fetch_live_52w(obj, token, "NSE", days=365)
        except Exception:
            errors += 1
            time.sleep(timeout_per)
            continue

        if not live52 or live52.get("w52_low", 0) == 0:
            skipped += 1
            time.sleep(0.05)
            continue

        w52_low  = live52["w52_low"]
        w52_high = live52["w52_high"]
        vol      = live52["ref_volume"]
        avg_vol  = live52["avg_vol_20d"]
        pct_ab   = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0

        # Apply 52W filter
        if pct_ab < min_pct or pct_ab > max_pct:
            time.sleep(timeout_per)
            continue

        vr, vl = compute_vol_ratio(vol, avg_vol)
        mcap_val = float(row.get("market_cap_cr", 0))

        results.append({
            "Name":           name,
            "Symbol":         sym,
            "LTP":            round(ltp, 2),
            "52W High":       round(w52_high, 2),
            "52W Low":        round(w52_low, 2),
            "% Above 52W":    round(pct_ab, 2),
            "Mkt Cap (Cr)":   round(mcap_val, 0) if mcap_val > 0 else "—",
            "Volume":         int(vol),
            "Avg Vol 20D":    int(avg_vol),
            "Vol Ratio":      vl,
            "_vr":            vr,
            "Status":         get_status(pct_ab),
        })
        time.sleep(timeout_per)

    prog_bar.empty()
    prog_text.empty()
    stat_box.empty()

    df_r = pd.DataFrame(results) if results else pd.DataFrame()
    if not df_r.empty:
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # Merge batches
    prev_df = data_store.load("watchlist_df")
    if (prev_df is not None and isinstance(prev_df, pd.DataFrame)
            and not prev_df.empty and batch_start > 1 and not df_r.empty):
        df_r = pd.concat([prev_df, df_r], ignore_index=True).drop_duplicates(subset=["Symbol"])
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)
        ts   = f"{ts} (merged batch {batch_start}–{end_idx})"
    elif not df_r.empty:
        ts   = f"{ts} (stocks {batch_start}–{end_idx} of {TOTAL})"

    save_df = df_r if not df_r.empty else pd.DataFrame()
    data_store.save("watchlist_df",   save_df)
    data_store.save("last_watchlist", ts)
    st.session_state["watchlist_data"] = save_df
    cached_df   = save_df
    cached_time = ts

    # Auto-advance batch start for next run
    st.session_state.wl_batch_start = end_idx + 1 if end_idx < TOTAL else 1

    elapsed_total = time.time() - scan_start
    st.success(
        f"✅ Done in {int(elapsed_total//60)}m {int(elapsed_total%60)}s · "
        f"**{len(save_df)} stocks** matched · {skipped} skipped · {errors} errors"
    )
    if end_idx < TOTAL:
        st.info(
            f"💡 Next batch ready: **Start from #{end_idx+1}** is already set. "
            f"Just click 🔄 FETCH WATCHLIST again to continue."
        )
        st.session_state.wl_batch_start = end_idx + 1

# ─────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────
wl_s = st.session_state.get("watchlist_data")
if wl_s is not None and isinstance(wl_s, pd.DataFrame) and not wl_s.empty:
    df_r = wl_s
elif cached_df is not None and isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
    df_r = cached_df
else:
    df_r = None

if df_r is None or df_r.empty:
    st.info("Set your filters → click **🔄 FETCH WATCHLIST**")
    st.stop()

# ── Metrics ───────────────────────────────────────────────────────
st.divider()
strong = int((df_r["Status"] == "🟢 STRONG").sum())
mod    = int((df_r["Status"] == "🟡 MODERATE").sum())
wtch   = int((df_r["Status"] == "🟠 WATCH").sum())
vbk    = int((df_r["_vr"] >= 1.5).sum())

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Stocks",   len(df_r))
m2.metric("🟢 STRONG",     strong)
m3.metric("🟡 MODERATE",   mod)
m4.metric("🟠 WATCH",      wtch)
m5.metric("🔥 Vol Breakout",vbk)

vb = df_r[df_r["_vr"] >= 1.5]
if not vb.empty:
    st.error("🔥 **VOLUME BREAKOUT:** " + "  ·  ".join(
        f"{r['Symbol']} ({r['Vol Ratio']})" for _, r in vb.iterrows()
    ))

st.divider()

# ── Display filters ───────────────────────────────────────────────
fc1, fc2 = st.columns(2)
with fc1:
    status_filter = st.multiselect(
        "Filter by Status",
        ["🟢 STRONG","🟡 MODERATE","🟠 WATCH"],
        default=["🟢 STRONG","🟡 MODERATE","🟠 WATCH"]
    )
with fc2:
    vol_only = st.checkbox("Show Volume Breakouts only 🔥", value=False)

df_show = df_r[df_r["Status"].isin(status_filter)].copy()
if vol_only:
    df_show = df_show[df_show["_vr"] >= 1.5]

# ── Styled table ──────────────────────────────────────────────────
def cs(v):
    if "STRONG"   in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "MODERATE" in str(v): return "background:#fff3cd;color:#856404;font-weight:700"
    if "WATCH"    in str(v): return "background:#ffe5d0;color:#7d4e00"
    return ""
def cv(v):
    if "🔥" in str(v): return "background:#d4edda;color:#155724;font-weight:700"
    if "⚡" in str(v): return "background:#fff3cd;color:#856404"
    return ""
def cpct(v):
    try:
        f = float(str(v).replace("%",""))
        if f <= 12: return "color:#155724;font-weight:600"
        if f <= 15: return "color:#856404"
        return "color:#7d4e00"
    except: return ""

show = ["Name","Symbol","LTP","52W High","52W Low","% Above 52W",
        "Mkt Cap (Cr)","Volume","Avg Vol 20D","Vol Ratio","Status"]
show = [c for c in show if c in df_show.columns]

fmt = {
    "LTP":         "₹{:,.2f}",
    "52W High":    "₹{:,.2f}",
    "52W Low":     "₹{:,.2f}",
    "% Above 52W": "{:.2f}%",
    "Volume":      "{:,}",
    "Avg Vol 20D": "{:,}",
}

if df_show.empty:
    st.warning("No stocks match the selected display filters.")
else:
    st.markdown(f"**{len(df_show)} stocks** matching filters")
    try:
        styled = (df_show[show].style
            .map(cs,   subset=["Status"])
            .map(cv,   subset=["Vol Ratio"])
            .map(cpct, subset=["% Above 52W"])
            .format(fmt, na_rep="—"))
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(df_show[show], use_container_width=True, hide_index=True)

if cached_time:
    st.caption(
        f"📅 Data from: **{cached_time}** · "
        f"Filters saved: {min_pct}–{max_pct}% above 52W · "
        f"No auto-refresh · Click 🔄 to update manually"
    )
