import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime
import pytz

st.set_page_config(page_title="📋 Watchlist", page_icon="📋", layout="wide")

from utils.sidebar import render_sidebar, require_app_login, check_session_alive
from utils import data_store

require_app_login()
render_sidebar()

from utils.angel_connect import (
    load_instrument_master, get_token,
    fetch_ltp, fetch_live_52w
)
from utils.indicators import compute_vol_ratio

# ── CSV paths — written automatically by the app, you never touch these ──
WATCHLIST_CSV    = "data/watchlist_cache.csv"
WATCHLIST_CSV_TS = "data/watchlist_cache_time.txt"

def load_csv_cache():
    """Load previously saved watchlist from disk. Returns DataFrame or empty."""
    if os.path.exists(WATCHLIST_CSV):
        try:
            return pd.read_csv(WATCHLIST_CSV)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def save_csv_cache(df, timestamp):
    """Save to CSV on disk — survives phone screen off / app switch / restart."""
    os.makedirs("data", exist_ok=True)
    df.to_csv(WATCHLIST_CSV, index=False)
    with open(WATCHLIST_CSV_TS, "w") as f:
        f.write(timestamp)

def load_csv_timestamp():
    if os.path.exists(WATCHLIST_CSV_TS):
        try:
            return open(WATCHLIST_CSV_TS).read().strip()
        except Exception:
            return ""
    return ""

# ── Load stock universe (your 2200+ stocks) ──────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    return pd.read_csv("data/stocks_full.csv")

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

# ── CSS ───────────────────────────────────────────────────────────
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
    f'Press <b>🔄 Update CSV</b> once before/after market · '
    f'Data saved to CSV — safe on mobile, no background fetch needed</div>',
    unsafe_allow_html=True
)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR FILTERS
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Scan Filters")
    st.divider()

    st.markdown("**📊 % Above 52W Low**")
    min_pct = st.number_input("Min %", 0.0, 500.0, value=st.session_state.wl_min_pct, step=0.5)
    max_pct = st.number_input("Max %", 0.0, 500.0, value=st.session_state.wl_max_pct, step=0.5)
    st.session_state.wl_min_pct = min_pct
    st.session_state.wl_max_pct = max_pct

    st.divider()

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
    )
    st.session_state.wl_sectors = sector_filter
    if sector_filter:
        st.caption(f"✅ {len(sector_filter)} sector(s) selected")

    st.divider()

    st.markdown("**💰 Market Cap (Crores ₹)**")
    mcap_apply = st.checkbox("Enable Market Cap Filter", value=st.session_state.wl_mcap_apply)
    st.session_state.wl_mcap_apply = mcap_apply

    if mcap_apply:
        mcap_cat = st.selectbox("Quick Select", [
            "Custom",
            "Micro Cap (< ₹500 Cr)",
            "Small Cap (₹500 – ₹5,000 Cr)",
            "Mid Cap (₹5,000 – ₹20,000 Cr)",
            "Large Cap (> ₹20,000 Cr)",
            "All sizes"
        ])
        if   mcap_cat == "Micro Cap (< ₹500 Cr)":         min_mcap = 0.0;     max_mcap = 500.0
        elif mcap_cat == "Small Cap (₹500 – ₹5,000 Cr)":  min_mcap = 500.0;   max_mcap = 5000.0
        elif mcap_cat == "Mid Cap (₹5,000 – ₹20,000 Cr)": min_mcap = 5000.0;  max_mcap = 20000.0
        elif mcap_cat == "Large Cap (> ₹20,000 Cr)":       min_mcap = 20000.0; max_mcap = 9999999.0
        elif mcap_cat == "All sizes":                       min_mcap = 0.0;     max_mcap = 9999999.0
        else:
            min_mcap = st.number_input("Min Market Cap (Cr)", 0.0, value=st.session_state.wl_min_mcap, step=100.0)
            max_mcap = st.number_input("Max Market Cap (Cr)", 0.0, value=9999999.0, step=1000.0)
        st.session_state.wl_min_mcap = min_mcap
        st.caption("⚠️ Market cap data for 2,207 of 2,242 stocks.")
    else:
        min_mcap = 0.0
        max_mcap = 9999999.0

    st.divider()

    st.markdown("### 📦 Batch Settings")
    batch_size = st.select_slider(
        "Batch Size",
        options=[50, 100, 200, 300, 500, 1000, 2242],
        value=st.session_state.wl_batch_size,
    )
    batch_start = st.number_input(
        "Start from stock #", min_value=1, max_value=TOTAL,
        value=st.session_state.wl_batch_start, step=1,
        help="Resume from here if previous run stopped"
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
# LOAD WHAT'S ALREADY SAVED ON DISK
# ─────────────────────────────────────────────────────────────────
csv_df   = load_csv_cache()
csv_time = load_csv_timestamp()

# ─────────────────────────────────────────────────────────────────
# BUTTONS ROW
# ─────────────────────────────────────────────────────────────────
connected = st.session_state.get("connected", False)

c_btn, c_clr, c_info = st.columns([1.4, 1, 3])

with c_btn:
    run_btn = st.button(
        "🔄 Update CSV",
        type="primary",
        use_container_width=True,
        help="Fetch all 2200+ stocks from Angel One → auto-save to CSV. Press once before/after market."
    )
with c_clr:
    clear_btn = st.button("🗑️ Clear CSV", use_container_width=True)
with c_info:
    if not csv_df.empty and csv_time:
        st.markdown(
            f'<div class="saved-banner">'
            f'💾 CSV last updated: <b>{csv_time}</b> · '
            f'<b>{len(csv_df)} stocks</b> saved · '
            f'Displaying from CSV — no live fetch needed'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="warn-banner">'
            '⚠️ No CSV saved yet — connect to Angel One → click <b>🔄 Update CSV</b> once'
            '</div>',
            unsafe_allow_html=True
        )

if clear_btn:
    for f in [WATCHLIST_CSV, WATCHLIST_CSV_TS]:
        if os.path.exists(f):
            os.remove(f)
    data_store.clear("watchlist_df")
    data_store.clear("last_watchlist")
    st.session_state.pop("watchlist_data", None)
    st.rerun()

if run_btn and not connected:
    st.error("❌ Please Connect to Angel One from the sidebar first.")
    st.stop()

def get_status(pct):
    if pct <= 12: return "🟢 STRONG"
    if pct <= 15: return "🟡 MODERATE"
    return "🟠 WATCH"

# ─────────────────────────────────────────────────────────────────
# 🔄 UPDATE CSV — fetches ALL 2200+ stocks → saves automatically
# ─────────────────────────────────────────────────────────────────
if run_btn and connected:
    if not check_session_alive():
        st.error("❌ Angel One session expired. Please Reconnect from sidebar.")
        st.stop()

    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    # Apply filters to the full 2200+ stock universe
    df_work = stocks_df.copy()

    if sector_filter:
        df_work = df_work[df_work["sector"].isin(sector_filter)]

    if mcap_apply and min_mcap > 0:
        known   = df_work[df_work["market_cap_cr"] > 0]
        unknown = df_work[df_work["market_cap_cr"] == 0]
        known   = known[(known["market_cap_cr"] >= min_mcap) & (known["market_cap_cr"] <= max_mcap)]
        df_work = pd.concat([known, unknown], ignore_index=True)

    # Batch slice (for resuming if it stopped mid-way)
    start_idx = batch_start - 1
    end_idx   = min(start_idx + batch_size, len(df_work))
    batch_df  = df_work.iloc[start_idx:end_idx].reset_index(drop=True)

    st.info(
        f"📡 Fetching stocks **#{batch_start} to #{end_idx}** of {len(df_work)} total · "
        f"Will auto-save to CSV when done ✅"
    )

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
        sector   = str(row.get("sector", "Unknown")).strip() or "Unknown"

        results.append({
            "Name":         name,
            "Symbol":       sym,
            "Sector":       sector,
            "LTP":          round(ltp, 2),
            "52W High":     round(w52_high, 2),
            "52W Low":      round(w52_low, 2),
            "% Above 52W":  round(pct_ab, 2),
            "Mkt Cap (Cr)": round(mcap_val, 2) if mcap_val > 0 else None,
            "Volume":       int(vol),
            "Avg Vol 20D":  int(avg_vol),
            "Vol Ratio":    vl,
            "_vr":          vr,
            "Status":       get_status(pct_ab),
        })
        time.sleep(timeout_per)

    prog_bar.empty(); prog_text.empty(); stat_box.empty()

    df_r = pd.DataFrame(results) if results else pd.DataFrame()
    if not df_r.empty:
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # Merge with previous batch if resuming
    if not csv_df.empty and batch_start > 1 and not df_r.empty:
        df_r = pd.concat([csv_df, df_r], ignore_index=True).drop_duplicates(subset=["Symbol"])
        df_r = df_r.sort_values("% Above 52W").reset_index(drop=True)
        ts   = f"{ts} (merged #{batch_start}–{end_idx})"
    elif not df_r.empty:
        ts   = f"{ts} (stocks {batch_start}–{end_idx} of {len(df_work)})"

    if not df_r.empty:
        # ✅ AUTO SAVE TO CSV — you did nothing, app saved it automatically
        save_csv_cache(df_r, ts)
        data_store.save("watchlist_df",   df_r)
        data_store.save("last_watchlist", ts)
        st.session_state["watchlist_data"] = df_r
        csv_df   = df_r
        csv_time = ts

    # Auto-advance batch start for next run
    next_start = end_idx + 1
    st.session_state.wl_batch_start = next_start if next_start <= len(df_work) else 1

    elapsed_total = time.time() - scan_start
    st.success(
        f"✅ Done in {int(elapsed_total//60)}m {int(elapsed_total%60)}s · "
        f"**{len(df_r) if not df_r.empty else 0} stocks matched** · "
        f"{skipped} skipped · {errors} errors · "
        f"💾 **CSV saved automatically!**"
    )
    if end_idx < len(df_work):
        st.info(
            f"💡 Batch done. Next batch auto-set to **#{next_start}** — "
            f"click 🔄 Update CSV again to continue."
        )

# ─────────────────────────────────────────────────────────────────
# DISPLAY — reads from CSV (no live fetch needed)
# ─────────────────────────────────────────────────────────────────
# Prefer session state (freshly fetched) over CSV
wl_s = st.session_state.get("watchlist_data")
if wl_s is not None and isinstance(wl_s, pd.DataFrame) and not wl_s.empty:
    df_r = wl_s
elif not csv_df.empty:
    df_r = csv_df
    # Sync to session + data_store so Signals page can use it
    st.session_state["watchlist_data"] = csv_df
    data_store.save("watchlist_df", csv_df)
else:
    df_r = None

if df_r is None or df_r.empty:
    st.info(
        "Connect to Angel One in sidebar → set your filters → "
        "click **🔄 Update CSV** once before or after market hours."
    )
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────
st.divider()
strong = int((df_r["Status"] == "🟢 STRONG").sum())
mod    = int((df_r["Status"] == "🟡 MODERATE").sum())
wtch   = int((df_r["Status"] == "🟠 WATCH").sum())
vbk    = int((df_r["_vr"] >= 1.5).sum()) if "_vr" in df_r.columns else 0

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Stocks",    len(df_r))
m2.metric("🟢 STRONG",      strong)
m3.metric("🟡 MODERATE",    mod)
m4.metric("🟠 WATCH",       wtch)
m5.metric("🔥 Vol Breakout", vbk)

if "_vr" in df_r.columns:
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
    available_sectors = sorted(df_r["Sector"].dropna().unique().tolist()) if "Sector" in df_r.columns else []
    sec_display = st.multiselect("Filter by Sector", available_sectors, default=[], placeholder="All sectors")
with fc3:
    vol_only = st.checkbox("🔥 Volume Breakouts only", value=False)

df_show = df_r[df_r["Status"].isin(status_filter)].copy()
if sec_display:
    df_show = df_show[df_show["Sector"].isin(sec_display)]
if vol_only and "_vr" in df_show.columns:
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

if csv_time:
    st.caption(
        f"📅 CSV updated: **{csv_time}** · "
        f"💾 Saved to disk · No live fetch needed to view · "
        f"Click 🔄 Update CSV to refresh"
    )
