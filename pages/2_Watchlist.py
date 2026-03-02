import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz

st.set_page_config(page_title="📋 Watchlist", page_icon="📋", layout="wide")

from utils.sidebar import render_sidebar, require_app_login, check_session_alive
from utils import data_store

require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.angel_connect import (
    load_instrument_master, get_token,
    fetch_ltp, fetch_live_52w
)
from utils.indicators import compute_vol_ratio

# ── Load stock universe ───────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv("data/stocks_full.csv")  # name, symbol, market_cap_cr, sector

stocks_df = load_stocks()
TOTAL = len(stocks_df)

# ── Persist filter settings ───────────────────────────────────────
def ss_init(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

ss_init("wl_min_pct",      1.0)
ss_init("wl_max_pct",      15.0)
ss_init("wl_min_mcap",     0.0)
ss_init("wl_mcap_apply",   False)
ss_init("wl_sectors",      [])
ss_init("wl_batch_size",   200)
ss_init("wl_batch_start",  1)
ss_init("wl_timeout",      0.12)

# ─────────────────────────────────────────────────────────────────
# PAGE HEADER
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
    f'<b>2,218 with sector</b> · <b>2,207 with market cap</b> · '
    f'All prices fetched live from Angel One · Filters remembered across pages</div>',
    unsafe_allow_html=True
)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR FILTERS
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Scan Filters")
    st.divider()

    # ── 52W Low filter ────────────────────────────────────────────
    st.markdown("**📊 % Above 52W Low**")
    min_pct = st.number_input(
        "Min %", 0.0, 500.0,
        value=st.session_state.wl_min_pct, step=0.5,
        help="Stock must be AT LEAST this % above 52W low"
    )
    max_pct = st.number_input(
        "Max %", 0.0, 500.0,
        value=st.session_state.wl_max_pct, step=0.5,
        help="Stock must be NO MORE than this % above 52W low"
    )
    st.session_state.wl_min_pct = min_pct
    st.session_state.wl_max_pct = max_pct

    st.divider()

    # ── Sector filter ─────────────────────────────────────────────
    st.markdown("**🏭 Sector Filter**")
    all_sectors = sorted([
        s for s in stocks_df["sector"].dropna().unique()
        if s and s.strip() not in ("Unknown", "")
    ])
    sector_filter = st.multiselect(
        "Select Sectors (empty = all)",
        options=all_sectors,
        default=st.session_state.wl_sectors,
        placeholder=f"All {len(all_sectors)} sectors",
        help=f"{len(all_sectors)} unique sectors available"
    )
    st.session_state.wl_sectors = sector_filter
    if sector_filter:
        st.caption(f"✅ {len(sector_filter)} sector(s) selected")

    st.divider()

    # ── Market Cap filter ─────────────────────────────────────────
    st.markdown("**💰 Market Cap (Crores ₹)**")
    mcap_apply = st.checkbox(
        "Enable Market Cap Filter",
        value=st.session_state.wl_mcap_apply
    )
    st.session_state.wl_mcap_apply = mcap_apply

    if mcap_apply:
        mcap_cat = st.selectbox(
            "Quick Select",
            ["Custom",
             "Micro Cap (< ₹500 Cr)",
             "Small Cap (₹500 – ₹5,000 Cr)",
             "Mid Cap (₹5,000 – ₹20,000 Cr)",
             "Large Cap (> ₹20,000 Cr)",
             "All sizes"],
        )
        if   mcap_cat == "Micro Cap (< ₹500 Cr)":         min_mcap = 0.0;     max_mcap = 500.0
        elif mcap_cat == "Small Cap (₹500 – ₹5,000 Cr)":  min_mcap = 500.0;   max_mcap = 5000.0
        elif mcap_cat == "Mid Cap (₹5,000 – ₹20,000 Cr)": min_mcap = 5000.0;  max_mcap = 20000.0
        elif mcap_cat == "Large Cap (> ₹20,000 Cr)":       min_mcap = 20000.0; max_mcap = 9999999.0
        elif mcap_cat == "All sizes":                       min_mcap = 0.0;     max_mcap = 9999999.0
        else:
            min_mcap = st.number_input("Min Market Cap (Cr)", 0.0, value=st.session_state.wl_min_mcap, step=100.0)
            max_mcap = st.number_input("Max Market Cap (Cr)", 0.0, value=9999999.0, step=1000.0)
        st.session_state.wl_min_mcap = min_mcap
        st.caption("⚠️ Market cap data for 2,207 of 2,242 stocks. Others pass through.")
    else:
        min_mcap = 0.0
        max_mcap = 9999999.0

    st.divider()

    # ── Batch settings ────────────────────────────────────────────
    st.markdown("### 📦 Batch Settings")
    batch_size = st.select_slider(
        "Batch Size",
        options=[50, 100, 200, 300, 500, 1000, 2242],
        value=st.session_state.wl_batch_size,
    )
    batch_start = st.number_input(
        "Start from stock #", min_value=1, max_value=TOTAL,
        value=st.session_state.wl_batch_start, step=1,
        help="Set this to resume after a timeout"
    )
    timeout_per = st.number_input(
        "Delay per stock (sec)", min_value=0.05, max_value=2.0,
        value=st.session_state.wl_timeout, step=0.01,
    )
    st.session_state.wl_batch_size  = batch_size
    st.session_state.wl_batch_start = batch_start
    st.session_state.wl_timeout     = timeout_per

    st.divider()
    st.caption("🟢 STRONG ≤12% · 🟡 MOD 12–15% · 🟠 WATCH >15%")

# ─────────────────────────────────────────────────────────────────
# BUTTONS + SAVED BANNER
# ─────────────────────────────────────────────────────────────────
cached_df   = data_store.load("watchlist_df")
cached_time = data_store.load("last_watchlist")

c_btn, c_clr, c_info = st.columns([1.2, 1, 3])
with c_btn:
    run_btn = st.button("🔄 FETCH WATCHLIST", type="primary", use_container_width=True)
with c_clr:
    clear_btn = st.button("🗑️ Clear Data", use_container_width=True)
with c_info:
    if cached_time:
        st.markdown(
            f'<div class="saved-banner">📦 Saved: <b>{cached_time}</b> · '
            f'No auto-refresh · Click 🔄 to update manually</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="warn-banner">No data yet — set filters → click 🔄 FETCH WATCHLIST</div>',
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
# FETCH LIVE
# ─────────────────────────────────────────────────────────────────
if run_btn:
    # Auto-reconnect if session dropped (phone locked, app switched, etc.)
    if not check_session_alive():
        st.error("❌ Angel One session expired and could not reconnect. Please use 🔄 Reconnect in sidebar.")
        st.stop()
    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    df_work = stocks_df.copy()

    # Pre-filter by sector
    if sector_filter:
        df_work = df_work[df_work["sector"].isin(sector_filter)]

    # Pre-filter by market cap (only where known)
    if mcap_apply and min_mcap > 0:
        known   = df_work[df_work["market_cap_cr"] > 0]
        unknown = df_work[df_work["market_cap_cr"] == 0]
        known   = known[(known["market_cap_cr"] >= min_mcap) & (known["market_cap_cr"] <= max_mcap)]
        df_work = pd.concat([known, unknown], ignore_index=True)

    # Batch slice
    start_idx = batch_start - 1
    end_idx   = min(start_idx + batch_size, len(df_work))
    batch_df  = df_work.iloc[start_idx:end_idx].reset_index(drop=True)

    st.divider()
    pc, sc = st.columns([3, 1])
    with pc:
        prog_bar  = st.progress(0)
        prog_text = st.empty()
    with sc:
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
            errors += 1; time.sleep(timeout_per); continue

        if not ltp or ltp == 0:
            skipped += 1; time.sleep(0.05); continue

        try:
            live52 = fetch_live_52w(obj, token, "NSE", days=365)
        except Exception:
            errors += 1; time.sleep(timeout_per); continue

        if not live52 or live52.get("w52_low", 0) == 0:
            skipped += 1; time.sleep(0.05); continue

        w52_low  = live52["w52_low"]
        w52_high = live52["w52_high"]
        vol      = live52["ref_volume"]
        avg_vol  = live52["avg_vol_20d"]
        pct_ab   = ((ltp - w52_low) / w52_low * 100) if w52_low > 0 else 0

        if pct_ab < min_pct or pct_ab > max_pct:
            time.sleep(timeout_per); continue

        vr, vl   = compute_vol_ratio(vol, avg_vol)
        mcap_val = float(row.get("market_cap_cr", 0))
        sector   = str(row.get("sector", "Unknown")).strip()
        if not sector: sector = "Unknown"

        results.append({
            "Name":          name,
            "Symbol":        sym,
            "Sector":        sector,
            "LTP":           round(ltp, 2),
            "52W High":      round(w52_high, 2),
            "52W Low":       round(w52_low, 2),
            "% Above 52W":   round(pct_ab, 2),
            "Mkt Cap (Cr)":  round(mcap_val, 2) if mcap_val > 0 else None,
            "Volume":        int(vol),
            "Avg Vol 20D":   int(avg_vol),
            "Vol Ratio":     vl,
            "_vr":           vr,
            "Status":        get_status(pct_ab),
        })
        time.sleep(timeout_per)

    prog_bar.empty(); prog_text.empty(); stat_box.empty()

    df_r = pd.DataFrame(results) if results else pd.DataFrame()
    if not df_r.empty:
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # Merge batches
    prev = data_store.load("watchlist_df")
    if (prev is not None and isinstance(prev, pd.DataFrame)
            and not prev.empty and batch_start > 1 and not df_r.empty):
        df_r = pd.concat([prev, df_r], ignore_index=True).drop_duplicates(subset=["Symbol"])
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)
        ts   = f"{ts} (merged #{batch_start}–{end_idx})"
    elif not df_r.empty:
        ts   = f"{ts} (stocks {batch_start}–{end_idx} of {len(df_work)})"

    save_df = df_r if not df_r.empty else pd.DataFrame()
    data_store.save("watchlist_df",   save_df)
    data_store.save("last_watchlist", ts)
    st.session_state["watchlist_data"] = save_df
    cached_df   = save_df
    cached_time = ts

    # Auto-advance batch for next run
    next_start = end_idx + 1
    st.session_state.wl_batch_start = next_start if next_start <= len(df_work) else 1

    elapsed_total = time.time() - scan_start
    st.success(
        f"✅ Done in {int(elapsed_total//60)}m {int(elapsed_total%60)}s · "
        f"**{len(save_df)} stocks matched** · {skipped} skipped · {errors} errors"
    )
    if end_idx < len(df_work):
        st.info(f"💡 Next batch: Start # auto-set to **{next_start}** — just click 🔄 again.")

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

# ── Summary metrics ───────────────────────────────────────────────
st.divider()
strong = int((df_r["Status"] == "🟢 STRONG").sum())
mod    = int((df_r["Status"] == "🟡 MODERATE").sum())
wtch   = int((df_r["Status"] == "🟠 WATCH").sum())
vbk    = int((df_r["_vr"] >= 1.5).sum())

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Stocks",    len(df_r))
m2.metric("🟢 STRONG",      strong)
m3.metric("🟡 MODERATE",    mod)
m4.metric("🟠 WATCH",       wtch)
m5.metric("🔥 Vol Breakout", vbk)

vb = df_r[df_r["_vr"] >= 1.5]
if not vb.empty:
    st.error("🔥 **VOLUME BREAKOUT:** " + "  ·  ".join(
        f"{r['Symbol']} ({r['Vol Ratio']})" for _, r in vb.iterrows()
    ))

st.divider()

# ── Display filters ───────────────────────────────────────────────
fc1, fc2, fc3 = st.columns(3)
with fc1:
    status_filter = st.multiselect(
        "Filter by Status",
        ["🟢 STRONG","🟡 MODERATE","🟠 WATCH"],
        default=["🟢 STRONG","🟡 MODERATE","🟠 WATCH"]
    )
with fc2:
    # Sector filter on results
    available_sectors = sorted(df_r["Sector"].dropna().unique().tolist()) if "Sector" in df_r.columns else []
    sec_display = st.multiselect("Filter by Sector", available_sectors, default=[],
                                  placeholder="All sectors")
with fc3:
    vol_only = st.checkbox("🔥 Volume Breakouts only", value=False)

df_show = df_r[df_r["Status"].isin(status_filter)].copy()
if sec_display:
    df_show = df_show[df_show["Sector"].isin(sec_display)]
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

show = ["Name","Symbol","Sector","LTP","52W High","52W Low",
        "% Above 52W","Mkt Cap (Cr)","Volume","Avg Vol 20D","Vol Ratio","Status"]
show = [c for c in show if c in df_show.columns]

fmt = {
    "LTP":          "₹{:,.2f}",
    "52W High":     "₹{:,.2f}",
    "52W Low":      "₹{:,.2f}",
    "% Above 52W":  "{:.2f}%",
    "Mkt Cap (Cr)": "₹{:,.2f}",
    "Volume":       "{:,}",
    "Avg Vol 20D":  "{:,}",
}

if df_show.empty:
    st.warning("No stocks match the selected filters.")
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
    st.caption(f"📅 Data from: **{cached_time}** · No auto-refresh · Click 🔄 to update manually")
