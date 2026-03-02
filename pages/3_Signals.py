import streamlit as st
import pandas as pd
import time
from datetime import datetime
import pytz

st.set_page_config(page_title="🧠 Signals", page_icon="🧠", layout="wide")

from utils.sidebar import render_sidebar, require_app_login, check_session_alive
from utils import data_store

require_app_login()
render_sidebar()

if not st.session_state.get("connected"):
    st.warning("👈 Please **Connect to Angel One** from the sidebar first.", icon="🔑")
    st.stop()

from utils.angel_connect import load_instrument_master, get_token, fetch_historical_ohlc, fetch_ltp
from utils.indicators import calculate_supertrend_signals, compute_risk, compute_vol_ratio

# ── Load stocks ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_stocks():
    try:    return pd.read_csv("data/stocks_full.csv")
    except: return pd.read_csv("data/stocks.csv")

stocks_df = load_stocks()

# ── Page header ───────────────────────────────────────────────────
st.markdown("""
<style>
.page-title{font-size:1.8rem;font-weight:700;color:#1A73E8;margin-bottom:2px;}
.sub-caption{color:#666;font-size:.88rem;margin-bottom:16px;}
.saved-banner{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;
              padding:10px 16px;color:#1b5e20;font-size:.9rem;margin-bottom:12px;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">🧠 SuperTrend Signals</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-caption">SuperTrend(10,3) · ATR(10) · EMA 23 · Swing High · 🟢 BUY / ⚪ WATCH · Data saved until you manually refresh</div>', unsafe_allow_html=True)

# ── Sidebar options ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Signal Settings")
    st.divider()
    use_wl = st.checkbox("Use Watchlist stocks only", value=True,
                         help="Recommended — runs only on your filtered watchlist stocks")
    st.divider()
    st.markdown("### 📦 Batch Settings")

    # Get watchlist size for batch options
    wl = st.session_state.get("watchlist_data")
    if wl is None or not isinstance(wl, pd.DataFrame) or wl.empty:
        wl = data_store.load("watchlist_df")
    wl_size = len(wl) if wl is not None and isinstance(wl, pd.DataFrame) else len(stocks_df)

    max_batch = wl_size if use_wl else len(stocks_df)
    batch_options = [25, 50, 100, 200, max_batch]
    batch_options = sorted(set(b for b in batch_options if b <= max_batch)) + ([max_batch] if max_batch not in batch_options else [])

    batch_size = st.select_slider(
        "Batch Size",
        options=batch_options,
        value=min(100, max_batch),
        help=f"Watchlist has {wl_size} stocks. Smaller batch = fewer timeouts."
    )
    batch_start = st.number_input(
        "Start from stock #", min_value=1, max_value=max_batch,
        value=1, step=1,
        help="Resume from here if previous run timed out"
    )
    timeout_per = st.number_input(
        "Delay per stock (sec)", min_value=0.05, max_value=2.0,
        value=0.10, step=0.01,
        help="Lower = faster. 0.10 is recommended."
    )
    st.divider()
    st.caption("🟢 BUY = Breakout + 5+ green days\n⚪ WATCH = GREEN, no breakout yet")

# ── Persistent data ───────────────────────────────────────────────
cached_df   = data_store.load("signals_df")
cached_meta = data_store.load("signals_meta")
cached_time = data_store.load("last_signals")

col_btn, col_clr, col_info = st.columns([1.2, 1, 3])
with col_btn:
    run_btn = st.button("🔄 RUN SIGNAL ANALYSIS", type="primary", use_container_width=True)
with col_clr:
    clear_btn = st.button("🗑️ Clear Data", use_container_width=True)
with col_info:
    if cached_time:
        st.markdown(f'<div class="saved-banner">📦 Saved data from <b>{cached_time}</b> — no auto-refresh. Click 🔄 to update manually.</div>', unsafe_allow_html=True)

if clear_btn:
    data_store.clear("signals_df")
    data_store.clear("signals_meta")
    data_store.clear("last_signals")
    st.session_state.pop("signals_data", None)
    st.rerun()

# ── Build universe ────────────────────────────────────────────────
def get_universe():
    wl = st.session_state.get("watchlist_data")
    if wl is None or not isinstance(wl, pd.DataFrame) or wl.empty:
        wl = data_store.load("watchlist_df")

    if use_wl and wl is not None and isinstance(wl, pd.DataFrame) and not wl.empty:
        rows = []
        for _, r in wl.iterrows():
            rows.append({
                "name":          r.get("Name",   r.get("name",   "Unknown")),
                "symbol":        f"NSE:{r.get('Symbol', r.get('symbol',''))}",
                "sector":        r.get("Sector", r.get("sector", "Unknown")),  # safe get
                "ref_ltp":       r.get("LTP",    r.get("ref_ltp", 0)),
                "w52_low":       r.get("52W Low",r.get("w52_low", 0)),
                "ref_volume":    r.get("Volume", r.get("ref_volume", 0)),
                "ref_avg_vol_20d": r.get("Avg Vol 20D", r.get("ref_avg_vol_20d", 0)),
            })
        return pd.DataFrame(rows)
    return stocks_df.copy()

# ── Run analysis ──────────────────────────────────────────────────
if run_btn:
    # Auto-reconnect if session dropped (phone locked, app switched, etc.)
    if not check_session_alive():
        st.error("❌ Angel One session expired and could not reconnect. Please use 🔄 Reconnect in sidebar.")
        st.stop()
    universe = get_universe()
    if universe.empty:
        st.warning("Build your **Watchlist** first, or uncheck 'Use Watchlist stocks only'.")
        st.stop()

    obj         = st.session_state.angel_obj
    instruments = load_instrument_master()

    # Apply batch slice
    start_idx = batch_start - 1
    end_idx   = min(start_idx + batch_size, len(universe))
    batch_uni = universe.iloc[start_idx:end_idx].reset_index(drop=True)

    src = "Watchlist" if use_wl else "All stocks"
    st.info(f"📡 Analysing **{len(batch_uni)} stocks** (#{batch_start}–{end_idx} of {len(universe)}) from {src}…")

    results, buy_list, watch_list, high_vol = [], [], [], []
    errors  = 0
    skipped = 0

    prog      = st.progress(0)
    prog_col, stat_col = st.columns([3, 1])
    with prog_col:
        lbl = st.empty()
    with stat_col:
        stat_box = st.empty()
    scan_start = time.time()

    for i, (_, row) in enumerate(batch_uni.iterrows()):
        sym  = str(row.get("symbol", ""))
        name = str(row.get("name", ""))
        pct_done = (i + 1) / len(batch_uni)

        elapsed = time.time() - scan_start
        eta_sec = (elapsed / (i + 1)) * (len(batch_uni) - i - 1) if i > 0 else 0
        eta_str = f"{int(eta_sec//60)}m {int(eta_sec%60)}s" if eta_sec > 60 else f"{int(eta_sec)}s"

        prog.progress(pct_done)
        lbl.markdown(
            f"**[{i+1}/{len(batch_uni)}]** `{sym.replace('NSE:','')}` — {name}  \n"
            f"⏱ Elapsed: {int(elapsed//60)}m{int(elapsed%60)}s · ETA: {eta_str} · "
            f"✅ {len(results)} found · ⏭ {skipped} skipped"
        )
        stat_box.metric("🟢 Found", len(results))

        # Token
        token = get_token(instruments, sym)
        if not token:
            skipped += 1
            continue

        tsym = sym.replace("NSE:", "")

        # Live LTP
        try:
            ltp = fetch_ltp(obj, "NSE", tsym, token) or row.get("ref_ltp", 0)
        except Exception:
            errors += 1
            time.sleep(timeout_per)
            continue

        # OHLC history
        try:
            ohlc = fetch_historical_ohlc(obj, token, "NSE", days=40)
        except Exception:
            errors += 1
            time.sleep(timeout_per)
            continue

        if not ohlc or len(ohlc) < 15:
            skipped += 1
            time.sleep(0.05)
            continue

        ohlc[-1]["close"] = ltp or ohlc[-1]["close"]

        # SuperTrend signal
        try:
            sig = calculate_supertrend_signals(ohlc)
        except Exception:
            errors += 1
            continue

        # Only GREEN stocks
        if sig["supertrend_status"] != "🟢 GREEN":
            time.sleep(timeout_per)
            continue

        vol     = ohlc[-1]["volume"]
        avg_vol = sum(c["volume"] for c in ohlc[-21:-1]) / 20 if len(ohlc) >= 21 else row.get("ref_avg_vol_20d", 0)
        vr, vl  = compute_vol_ratio(vol, avg_vol)
        if vr >= 1.5:
            high_vol.append(f"{tsym}({vr:.1f}x)")

        risk   = compute_risk(ltp, sig["ema23"])
        signal = "🟢 BUY" if sig["is_breakout"] else "⚪ WATCH"
        (buy_list if signal == "🟢 BUY" else watch_list).append(tsym)

        w52l   = row.get("w52_low", 0)
        pct_ab = ((ltp - w52l) / w52l * 100) if w52l > 0 else 0

        results.append({
            "Symbol":      tsym,
            "Sector":      row.get("sector", "—"),
            "LTP":         round(ltp, 2),
            "% Above 52W": round(pct_ab, 2),
            "Days Green":  sig["days_green"],
            "Flat?":       "✅" if sig["is_flat"] else "❌",
            "Swing High":  sig["swing_high"] or "—",
            "SH Date":     sig["swing_high_date"] or "—",
            "Breakout?":   "✅" if sig["is_breakout"] else "❌",
            "23-EMA":      sig["ema23"] or "—",
            "SL 5%":       risk["sl_5pct"],
            "Rec SL":      risk["recommended_sl"],
            "Risk %":      risk["risk_ema_pct"],
            "Vol Ratio":   vl,
            "_vr":         vr,
            "Risk Status": risk["risk_status"],
            "SIGNAL":      signal,
        })
        time.sleep(timeout_per)

    prog.empty()
    lbl.empty()
    stat_box.empty()

    df_new = pd.DataFrame(results) if results else pd.DataFrame()
    meta   = {"buy": buy_list, "watch": watch_list, "high_vol": high_vol, "total": len(universe)}
    ist    = pytz.timezone("Asia/Kolkata")
    ts     = datetime.now(ist).strftime("%d %b %Y %H:%M IST")

    # Merge batches
    prev_df = data_store.load("signals_df")
    if prev_df is not None and isinstance(prev_df, pd.DataFrame) and not prev_df.empty and batch_start > 1 and not df_new.empty:
        df_new = pd.concat([prev_df, df_new], ignore_index=True).drop_duplicates(subset=["Symbol"])
        ts = f"{ts} (merged batch {batch_start}–{end_idx})"
    elif not df_new.empty:
        ts = f"{ts} (stocks {batch_start}–{end_idx} of {len(universe)})"

    save_df = df_new if not df_new.empty else pd.DataFrame()
    data_store.save("signals_df",   save_df)
    data_store.save("signals_meta", meta)
    data_store.save("last_signals", ts)
    st.session_state["signals_data"] = save_df

    cached_df   = save_df
    cached_meta = meta
    cached_time = ts

    elapsed_total = time.time() - scan_start
    st.success(
        f"✅ Done in {int(elapsed_total//60)}m {int(elapsed_total%60)}s · "
        f"**{len(results)} GREEN stocks** found · {skipped} skipped · {errors} errors"
    )
    if end_idx < len(universe):
        st.info(f"💡 Next batch: set **Start from stock #** to **{end_idx + 1}** and run again.")

# ── Display ───────────────────────────────────────────────────────
df = st.session_state.get("signals_data")
if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    df = cached_df

meta = cached_meta or {}

if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    if not run_btn:
        st.info("Build **Watchlist** first → then click **🔄 RUN SIGNAL ANALYSIS**")
    else:
        st.warning("No GREEN SuperTrend stocks found in this batch.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────
st.divider()
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Analysed",    meta.get("total", len(df)))
c2.metric("🟢 GREEN",    len(df))
c3.metric("🟢 BUY",      len(meta.get("buy",[])))
c4.metric("⚪ WATCH",    len(meta.get("watch",[])))
c5.metric("🔥 High Vol", len(meta.get("high_vol",[])))

if meta.get("buy"):
    st.success("🟢 **BUY SIGNALS:** " + "  ·  ".join(meta["buy"]))
if meta.get("high_vol"):
    st.error("🔥 **HIGH VOLUME:** " + "  ·  ".join(meta["high_vol"]))

st.divider()

# ── Display filters ───────────────────────────────────────────────
f1, f2 = st.columns(2)
fs = f1.multiselect("Filter Signal",  ["🟢 BUY","⚪ WATCH"], ["🟢 BUY","⚪ WATCH"])
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

if df_d.empty:
    st.warning("No stocks match the current filters.")
else:
    st.markdown(f"**{len(df_d)} stocks** matching filters")
    styled = (df_d.style
        .map(ss, subset=["SIGNAL"])
        .map(sr, subset=["Risk Status"])
        .map(sv, subset=["Vol Ratio"])
        .format({"LTP":"₹{:,.2f}","% Above 52W":"{:.2f}%",
                 "SL 5%":"₹{:,.2f}","Rec SL":"₹{:,.2f}","Risk %":"{:.2f}%"}, na_rep="—"))
    st.dataframe(styled, use_container_width=True, hide_index=True)

if cached_time:
    st.caption(f"📅 Data from: **{cached_time}** · No auto-refresh · Click 🔄 to update manually")
