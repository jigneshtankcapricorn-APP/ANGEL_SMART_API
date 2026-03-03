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

from utils.angel_connect import load_instrument_master, get_token, fetch_ltp, fetch_live_52w
from utils.indicators import compute_vol_ratio

# ─────────────────────────────────────────────────────────────────
# FILE PATHS
# stocks_full.csv  → your original 2242 stocks (symbol, name, sector, market_cap_cr)
# stocks_live.csv  → enriched with live data (LTP, 52W, Volume) — written by Update CSV button
# ─────────────────────────────────────────────────────────────────
STOCKS_BASE = "data/stocks_full.csv"
STOCKS_LIVE = "data/stocks_live.csv"
LIVE_TS     = "data/stocks_live_time.txt"

@st.cache_data(show_spinner=False)
def load_base_stocks():
    return pd.read_csv(STOCKS_BASE)

def load_live_csv():
    if os.path.exists(STOCKS_LIVE):
        try:
            return pd.read_csv(STOCKS_LIVE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def load_live_timestamp():
    if os.path.exists(LIVE_TS):
        try:
            return open(LIVE_TS).read().strip()
        except:
            return ""
    return ""

def save_live_csv(df, timestamp):
    os.makedirs("data", exist_ok=True)
    df.to_csv(STOCKS_LIVE, index=False)
    with open(LIVE_TS, "w") as f:
        f.write(timestamp)

stocks_base = load_base_stocks()
TOTAL       = len(stocks_base)
live_df     = load_live_csv()
live_time   = load_live_timestamp()

# ── CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.page-title   {font-size:1.8rem;font-weight:700;color:#1A73E8;margin-bottom:2px;}
.sub-caption  {color:#666;font-size:.88rem;margin-bottom:16px;}
.csv-box      {background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;
               padding:12px 16px;color:#1b5e20;font-size:.93rem;margin-bottom:4px;}
.csv-warn     {background:#fff3cd;border:1px solid #ffc107;border-radius:8px;
               padding:12px 16px;color:#856404;font-size:.93rem;margin-bottom:4px;}
.csv-section  {background:#f8f9fa;border:1px solid #dee2e6;border-radius:10px;
               padding:16px;margin-bottom:20px;}
.section-divider{border-top:2px solid #1A73E8;margin:20px 0 16px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">📋 Watchlist</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-caption">'
    f'<b>Step 1:</b> Update CSV once (before/after market) → '
    f'<b>Step 2:</b> Set filters → Watchlist reads from CSV instantly, no API needed'
    f'</div>',
    unsafe_allow_html=True
)

# ═════════════════════════════════════════════════════════════════
# SECTION 1 — UPDATE CSV  (completely separate from Watchlist)
# ═════════════════════════════════════════════════════════════════
st.markdown("### 📥 Step 1 — Update CSV")
st.caption(
    "Fetches LTP, 52W High/Low and Volume for all 2,242 stocks from Angel One → "
    "saves to stocks_live.csv. Do this once before or after market. "
    "Watchlist below reads from this file."
)

connected = st.session_state.get("connected", False)

# Batch settings for CSV update (in an expander to keep UI clean)
with st.expander("⚙️ Batch Settings for CSV Update", expanded=False):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        csv_batch_size = st.select_slider(
            "Batch Size",
            options=[200, 300, 500, 1000, 2242],
            value=st.session_state.get("csv_batch_size", 500),
        )
        st.session_state["csv_batch_size"] = csv_batch_size
    with col_b:
        csv_batch_start = st.number_input(
            "Start from stock #", min_value=1, max_value=TOTAL,
            value=st.session_state.get("csv_batch_start", 1), step=1,
            help="Auto-advances after each run. Change only if you want to restart."
        )
        st.session_state["csv_batch_start"] = csv_batch_start
    with col_c:
        csv_timeout = st.number_input(
            "Delay per stock (sec)", min_value=0.05, max_value=2.0,
            value=st.session_state.get("csv_timeout", 0.12), step=0.01,
        )
        st.session_state["csv_timeout"] = csv_timeout

# ── Update CSV button row ─────────────────────────────────────────
btn_col, info_col = st.columns([1.5, 4])

with btn_col:
    update_csv_btn = st.button(
        "📥 Update CSV",
        type="primary",
        use_container_width=True,
        disabled=not connected,
        help="Fetch all 2242 stocks → auto-save to stocks_live.csv"
    )
    if not connected:
        st.caption("⚠️ Connect Angel One first")

with info_col:
    if live_time:
        remaining = TOTAL - (len(live_df) if not live_df.empty else 0)
        st.markdown(
            f'<div class="csv-box">'
            f'✅ Last CSV update: <b>{live_time}</b> &nbsp;|&nbsp; '
            f'<b>{len(live_df):,} stocks</b> in CSV'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="csv-warn">'
            '⚠️ <b>CSV not updated yet.</b> Connect to Angel One → click 📥 Update CSV first. '
            'Watchlist will not work until CSV has data.'
            '</div>',
            unsafe_allow_html=True
        )

# ── Run CSV Update ────────────────────────────────────────────────
if update_csv_btn:
    if not connected:
        st.error("❌ Please Connect to Angel One from the sidebar first.")
        st.stop()

    if not check_session_alive():
        st.error("❌ Angel One session expired. Please Reconnect from sidebar.")
        st.stop()

    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    start_idx = csv_batch_start - 1
    end_idx   = min(start_idx + csv_batch_size, TOTAL)
    batch_df  = stocks_base.iloc[start_idx:end_idx].reset_index(drop=True)

    st.info(
        f"📡 Fetching live data for stocks **#{csv_batch_start} to #{end_idx}** "
        f"of {TOTAL} total → will auto-save to CSV"
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
            f"⏱ {int(elapsed//60)}m{int(elapsed%60)}s elapsed · ETA: {eta_str} · "
            f"✅ {len(results)} fetched · ⏭ {skipped} skipped"
        )
        stat_box.metric("✅ Fetched", len(results))

        token = get_token(instruments, sym)
        if not token:
            skipped += 1
            continue

        try:
            ltp = fetch_ltp(obj, "NSE", sym, token)
        except Exception:
            errors += 1; time.sleep(csv_timeout); continue

        if not ltp or ltp == 0:
            skipped += 1; time.sleep(0.05); continue

        try:
            live52 = fetch_live_52w(obj, token, "NSE", days=365)
        except Exception:
            errors += 1; time.sleep(csv_timeout); continue

        if not live52 or live52.get("w52_low", 0) == 0:
            skipped += 1; time.sleep(0.05); continue

        results.append({
            "symbol":        sym,
            "name":          name,
            "sector":        str(row.get("sector", "Unknown")).strip() or "Unknown",
            "market_cap_cr": float(row.get("market_cap_cr", 0)),
            "ltp":           round(ltp, 2),
            "w52_high":      round(live52["w52_high"], 2),
            "w52_low":       round(live52["w52_low"], 2),
            "volume":        int(live52["ref_volume"]),
            "avg_vol_20d":   int(live52["avg_vol_20d"]),
        })
        time.sleep(csv_timeout)

    prog_bar.empty(); prog_text.empty(); stat_box.empty()

    df_new = pd.DataFrame(results) if results else pd.DataFrame()

    ist = pytz.timezone("Asia/Kolkata")
    ts  = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # Merge with previously saved CSV if resuming
    if not live_df.empty and csv_batch_start > 1 and not df_new.empty:
        df_merged = pd.concat([live_df, df_new], ignore_index=True).drop_duplicates(subset=["symbol"])
        ts = f"{ts} · batch #{csv_batch_start}–{end_idx} merged"
    elif not df_new.empty:
        df_merged = df_new
        ts = f"{ts} · stocks #{csv_batch_start}–{end_idx} of {TOTAL}"
    else:
        df_merged = live_df

    if not df_merged.empty:
        save_live_csv(df_merged, ts)
        live_df   = df_merged
        live_time = ts
        st.cache_data.clear()

    # Auto-advance batch start
    next_start = end_idx + 1
    st.session_state["csv_batch_start"] = next_start if next_start <= TOTAL else 1

    elapsed_total = time.time() - scan_start
    st.success(
        f"✅ CSV updated in {int(elapsed_total//60)}m {int(elapsed_total%60)}s · "
        f"**{len(df_merged):,} total stocks in CSV** · "
        f"{skipped} skipped · {errors} errors · 💾 Saved to stocks_live.csv"
    )
    if end_idx < TOTAL:
        st.info(
            f"💡 Batch complete. Next batch auto-set to **#{next_start}** — "
            f"click 📥 Update CSV again to continue."
        )
    else:
        st.balloons()
        st.success("🎉 All stocks updated in CSV!")

# ═════════════════════════════════════════════════════════════════
# SECTION 2 — WATCHLIST  (reads from CSV only, zero API calls)
# ═════════════════════════════════════════════════════════════════
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### 📋 Step 2 — Watchlist (reads from CSV)")

# ── Block if CSV not ready ────────────────────────────────────────
if live_df.empty:
    st.warning(
        "⚠️ **CSV is empty.** Please update CSV first using the 📥 Update CSV button above. "
        "Watchlist works only after at least one full (or partial) CSV update."
    )
    st.stop()

# ── Compute % Above 52W for all stocks in CSV ─────────────────────
def get_status(pct):
    if pct <= 12: return "🟢 STRONG"
    if pct <= 15: return "🟡 MODERATE"
    return "🟠 WATCH"

df_calc = live_df.copy()
df_calc["pct_above_52w"] = df_calc.apply(
    lambda r: round(((r["ltp"] - r["w52_low"]) / r["w52_low"] * 100), 2)
    if r.get("w52_low", 0) > 0 else 0,
    axis=1
)
df_calc["vol_ratio_raw"], df_calc["vol_ratio_lbl"] = zip(
    *df_calc.apply(lambda r: compute_vol_ratio(r.get("volume", 0), r.get("avg_vol_20d", 0)), axis=1)
)
df_calc["status"] = df_calc["pct_above_52w"].apply(get_status)

# ── Sidebar filters ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Watchlist Filters")
    st.caption("Filters apply to CSV data — no API call")
    st.divider()

    st.markdown("**📊 % Above 52W Low**")
    min_pct = st.number_input("Min %", 0.0, 500.0, value=1.0,  step=0.5)
    max_pct = st.number_input("Max %", 0.0, 500.0, value=15.0, step=0.5)

    st.divider()
    st.markdown("**🏭 Sector Filter**")
    all_sectors = sorted([
        s for s in df_calc["sector"].dropna().unique()
        if s and s.strip() not in ("Unknown", "")
    ])
    sector_filter = st.multiselect(
        "Select Sectors (empty = all)",
        options=all_sectors,
        default=[],
        placeholder=f"All {len(all_sectors)} sectors",
    )

    st.divider()
    st.markdown("**💰 Market Cap (Crores ₹)**")
    mcap_apply = st.checkbox("Enable Market Cap Filter", value=False)
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
            min_mcap = st.number_input("Min Market Cap (Cr)", 0.0, value=0.0, step=100.0)
            max_mcap = st.number_input("Max Market Cap (Cr)", 0.0, value=9999999.0, step=1000.0)
    else:
        min_mcap, max_mcap = 0.0, 9999999.0

    st.divider()
    vol_only = st.checkbox("🔥 Volume Breakouts only", value=False)
    st.divider()
    st.caption("🟢 STRONG ≤12% · 🟡 MOD 12–15% · 🟠 WATCH >15%")

# ── FETCH FROM CSV BUTTON ────────────────────────────────────────
st.markdown("#### 🔍 Fetch from CSV")
fetch_col, fetch_info_col = st.columns([1.5, 4])
with fetch_col:
    fetch_btn = st.button(
        "🔍 Fetch from CSV",
        type="primary",
        use_container_width=True,
        help="Apply your sidebar filters and display matching stocks from saved CSV"
    )
with fetch_info_col:
    st.markdown(
        '<div style="background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;'
        'padding:10px 16px;color:#0d47a1;font-size:.9rem;">'
        'Set your filters in the sidebar → click <b>🔍 Fetch from CSV</b> to display results'
        '</div>',
        unsafe_allow_html=True
    )

if not fetch_btn and not st.session_state.get("wl_fetched_once", False):
    st.info("👈 Set your filters in the sidebar → click **🔍 Fetch from CSV** to see results.")
    st.stop()

if fetch_btn:
    st.session_state["wl_fetched_once"] = True

st.divider()

# ── Apply filters (from CSV — no API call) ────────────────────────
df_filtered = df_calc[
    (df_calc["pct_above_52w"] >= min_pct) &
    (df_calc["pct_above_52w"] <= max_pct)
].copy()

if sector_filter:
    df_filtered = df_filtered[df_filtered["sector"].isin(sector_filter)]

if mcap_apply:
    known   = df_filtered[df_filtered["market_cap_cr"] > 0]
    unknown = df_filtered[df_filtered["market_cap_cr"] == 0]
    known   = known[(known["market_cap_cr"] >= min_mcap) & (known["market_cap_cr"] <= max_mcap)]
    df_filtered = pd.concat([known, unknown], ignore_index=True)

if vol_only:
    df_filtered = df_filtered[df_filtered["vol_ratio_raw"] >= 1.5]

df_filtered = df_filtered.sort_values("pct_above_52w").reset_index(drop=True)

# Sync to data_store so Signals page can use it
if not df_filtered.empty:
    sync_df = df_filtered.rename(columns={
        "name":          "Name",
        "symbol":        "Symbol",
        "sector":        "Sector",
        "ltp":           "LTP",
        "w52_high":      "52W High",
        "w52_low":       "52W Low",
        "pct_above_52w": "% Above 52W",
        "market_cap_cr": "Mkt Cap (Cr)",
        "volume":        "Volume",
        "avg_vol_20d":   "Avg Vol 20D",
        "vol_ratio_lbl": "Vol Ratio",
        "vol_ratio_raw": "_vr",
        "status":        "Status",
    })
    data_store.save("watchlist_df", sync_df)
    st.session_state["watchlist_data"] = sync_df

# ── Summary metrics ───────────────────────────────────────────────
strong = int((df_filtered["status"] == "🟢 STRONG").sum())
mod    = int((df_filtered["status"] == "🟡 MODERATE").sum())
wtch   = int((df_filtered["status"] == "🟠 WATCH").sum())
vbk    = int((df_filtered["vol_ratio_raw"] >= 1.5).sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Stocks",    len(df_filtered))
m2.metric("🟢 STRONG",      strong)
m3.metric("🟡 MODERATE",    mod)
m4.metric("🟠 WATCH",       wtch)
m5.metric("🔥 Vol Breakout", vbk)

vb = df_filtered[df_filtered["vol_ratio_raw"] >= 1.5]
if not vb.empty:
    st.error("🔥 **VOLUME BREAKOUT:** " + "  ·  ".join(
        f"{r['symbol']} ({r['vol_ratio_lbl']})" for _, r in vb.iterrows()
    ))

st.divider()

if df_filtered.empty:
    st.warning("No stocks match your current filters. Try adjusting % range or sector.")
    st.stop()

# ── Status filter ─────────────────────────────────────────────────
status_sel = st.multiselect(
    "Filter by Status",
    ["🟢 STRONG", "🟡 MODERATE", "🟠 WATCH"],
    default=["🟢 STRONG", "🟡 MODERATE", "🟠 WATCH"]
)
df_show = df_filtered[df_filtered["status"].isin(status_sel)].copy()

# ── Rename for display ────────────────────────────────────────────
df_disp = df_show.rename(columns={
    "name":          "Name",
    "symbol":        "Symbol",
    "sector":        "Sector",
    "ltp":           "LTP",
    "w52_high":      "52W High",
    "w52_low":       "52W Low",
    "pct_above_52w": "% Above 52W",
    "market_cap_cr": "Mkt Cap (Cr)",
    "volume":        "Volume",
    "avg_vol_20d":   "Avg Vol 20D",
    "vol_ratio_lbl": "Vol Ratio",
    "status":        "Status",
})

show_cols = ["Name","Symbol","Sector","LTP","52W High","52W Low",
             "% Above 52W","Mkt Cap (Cr)","Volume","Avg Vol 20D","Vol Ratio","Status"]
show_cols = [c for c in show_cols if c in df_disp.columns]

fmt = {
    "LTP":          "₹{:,.2f}",
    "52W High":     "₹{:,.2f}",
    "52W Low":      "₹{:,.2f}",
    "% Above 52W":  "{:.2f}%",
    "Mkt Cap (Cr)": "₹{:,.2f}",
    "Volume":       "{:,}",
    "Avg Vol 20D":  "{:,}",
}

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

st.markdown(f"**{len(df_disp)} stocks** matching filters")
try:
    styled = (df_disp[show_cols].style
        .map(cs,   subset=["Status"])
        .map(cv,   subset=["Vol Ratio"])
        .map(cpct, subset=["% Above 52W"])
        .format(fmt, na_rep="—"))
    st.dataframe(styled, use_container_width=True, hide_index=True)
except Exception:
    st.dataframe(df_disp[show_cols], use_container_width=True, hide_index=True)

st.caption(
    f"📅 CSV data from: **{live_time}** · "
    f"Displaying from saved CSV — no live API call · "
    f"Click 📥 Update CSV above to refresh data"
)
