"""
indicators.py
Exact Python port of the AppScript SuperTrend, ATR, EMA logic.
No shortcuts. No simplifications.
"""


def calculate_atr(ohlc_data, period=10):
    """
    Wilder ATR — exact port from AppScript calculateSuperTrendSignals().
    Returns list of ATR values (None for first period-1 entries).
    """
    true_ranges = []
    for i in range(1, len(ohlc_data)):
        h = ohlc_data[i]['high']
        l = ohlc_data[i]['low']
        pc = ohlc_data[i - 1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)

    atr_values = []
    for i in range(len(true_ranges)):
        if i < period - 1:
            atr_values.append(None)
        elif i == period - 1:
            atr_values.append(sum(true_ranges[:period]) / period)
        else:
            prev = atr_values[i - 1]
            atr_values.append(((prev * (period - 1)) + true_ranges[i]) / period)

    return atr_values


def calculate_ema(closes, period=23):
    """
    23-period EMA — exact port from AppScript Step 9.
    Returns final EMA value or None if insufficient data.
    """
    if len(closes) < period:
        return None
    sma = sum(closes[:period]) / period
    mult = 2 / (period + 1)
    ema = sma
    for c in closes[period:]:
        ema = (c * mult) + (ema * (1 - mult))
    return ema


def calculate_supertrend_signals(ohlc_data, period=10, multiplier=3):
    """
    Full SuperTrend analysis — exact port of calculateSuperTrendSignals() AppScript.

    Parameters
    ----------
    ohlc_data : list of dicts with keys: date, open, high, low, close, volume
    period    : ATR period (default 10)
    multiplier: SuperTrend multiplier (default 3)

    Returns
    -------
    dict with:
        supertrend_status : '🟢 GREEN' or '🔴 RED'
        days_green        : int
        is_flat           : bool  (ST range < 3.5% over 5+ green days)
        swing_high        : float or None
        swing_high_date   : str or None   (dd-Mon-YYYY)
        is_breakout       : bool  (LTP > swing_high, bullish close, 5+ green days)
        ema23             : float or None
    """
    result = {
        'supertrend_status': '🔴 RED',
        'days_green': 0,
        'is_flat': False,
        'swing_high': None,
        'swing_high_date': None,
        'is_breakout': False,
        'ema23': None,
    }

    if not ohlc_data or len(ohlc_data) < 12:
        return result

    current_ltp = ohlc_data[-1]['close']

    # ── Steps 1 & 2: True Range → ATR ──────────────────────────────────────
    atr_values = calculate_atr(ohlc_data, period)

    # ── Step 3: SuperTrend (10, 3) ─────────────────────────────────────────
    directions = []
    st_values = []
    prev_final_upper = 0.0
    prev_final_lower = 0.0
    prev_st = 0.0

    for i in range(len(ohlc_data) - 1):
        atr = atr_values[i]
        if atr is None or i < period:
            directions.append(None)
            st_values.append(None)
            continue

        day = ohlc_data[i + 1]
        hl_avg = (day['high'] + day['low']) / 2.0
        basic_upper = hl_avg + (multiplier * atr)
        basic_lower = hl_avg - (multiplier * atr)
        prev_close = ohlc_data[i]['close']

        # Final upper band
        if basic_upper < prev_final_upper or prev_close > prev_final_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_final_upper

        # Final lower band
        if basic_lower > prev_final_lower or prev_close < prev_final_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_final_lower

        # SuperTrend value & direction
        if prev_st == prev_final_upper:
            if day['close'] <= final_upper:
                st = final_upper
                direction = -1
            else:
                st = final_lower
                direction = 1
        else:
            if day['close'] >= final_lower:
                st = final_lower
                direction = 1
            else:
                st = final_upper
                direction = -1

        directions.append(direction)
        st_values.append(st)
        prev_final_upper = final_upper
        prev_final_lower = final_lower
        prev_st = st

    # ── Step 4: Current SuperTrend Status ──────────────────────────────────
    last_dir = None
    for d in reversed(directions):
        if d is not None:
            last_dir = d
            break
    result['supertrend_status'] = '🟢 GREEN' if last_dir == 1 else '🔴 RED'

    # ── Step 5: Count Consecutive Green Days ───────────────────────────────
    days_green = 0
    for d in reversed(directions):
        if d == 1:
            days_green += 1
        elif d == -1:
            break
    result['days_green'] = days_green

    # ── Step 6: Swing High + Date (with 7-day freeze logic) ────────────────
    swing_high = None
    swing_high_date = None
    transition_index = -1

    # Find the last RED→GREEN transition
    for i in range(1, len(directions)):
        if directions[i - 1] == -1 and directions[i] == 1:
            transition_index = i

    if transition_index != -1 and days_green >= 5:
        days_since_transition = (len(ohlc_data) - 1) - (transition_index + 1)
        green_day_index = transition_index + 1

        if 0 <= green_day_index < len(ohlc_data):
            swing_high = ohlc_data[green_day_index]['high']
            swing_high_date = ohlc_data[green_day_index].get('date', '')

            # FREEZE after 7 days — only update within 7 days of transition
            if days_since_transition <= 7:
                flat_start = max(0, len(ohlc_data) - days_green)
                # Exclude today: i < len(ohlc_data) - 1
                for i in range(flat_start, len(ohlc_data) - 1):
                    if ohlc_data[i]['high'] > swing_high:
                        swing_high = ohlc_data[i]['high']
                        swing_high_date = ohlc_data[i].get('date', '')

    if swing_high and swing_high > 0:
        result['swing_high'] = round(swing_high, 2)
        result['swing_high_date'] = str(swing_high_date)[:10] if swing_high_date else None

    # ── Step 7: Flat Zone (ST range < 3.5% over 5+ green days) ────────────
    if days_green >= 5:
        start_idx = max(0, len(st_values) - days_green)
        st_in_green = [v for v in st_values[start_idx:] if v is not None]
        if len(st_in_green) >= 5:
            min_st = min(st_in_green)
            max_st = max(st_in_green)
            st_range_pct = ((max_st - min_st) / min_st * 100) if min_st > 0 else 0
            result['is_flat'] = st_range_pct < 3.5

    # ── Step 8: Breakout Detection (requires 5+ green days) ────────────────
    if result['swing_high'] and days_green >= 5:
        last_candle = ohlc_data[-1]
        if (current_ltp > result['swing_high'] and
                last_candle['close'] > last_candle['open']):
            result['is_breakout'] = True

    # ── Step 9: 23-Day EMA ─────────────────────────────────────────────────
    closes = [d['close'] for d in ohlc_data]
    ema_val = calculate_ema(closes, 23)
    if ema_val:
        result['ema23'] = round(ema_val, 2)

    return result


def compute_risk(ltp, ema23, sl_pct=5.0):
    """
    Risk calculations — mirrors AppScript logic.
    Returns dict with sl_5pct, recommended_sl, risk_ema_pct, risk_status.
    """
    sl_5pct = round(ltp * (1 - sl_pct / 100), 2)

    if ema23 and ema23 > 0:
        recommended_sl = round(max(ema23, sl_5pct), 2)
        risk_ema_pct = round((ltp - ema23) / ltp * 100, 2)
    else:
        recommended_sl = sl_5pct
        risk_ema_pct = sl_pct

    if risk_ema_pct > 7:
        risk_status = '⚠️ HIGH RISK'
    elif risk_ema_pct > 5:
        risk_status = '🟡 MODERATE'
    else:
        risk_status = '🟢 LOW RISK'

    return {
        'sl_5pct': sl_5pct,
        'recommended_sl': recommended_sl,
        'risk_ema_pct': risk_ema_pct,
        'risk_pct_5': sl_pct,
        'risk_status': risk_status,
    }


def compute_vol_ratio(volume, avg_vol_20d):
    """Volume ratio with emoji indicator"""
    if not avg_vol_20d or avg_vol_20d == 0:
        return 0, '—'
    ratio = round(volume / avg_vol_20d, 2)
    if ratio >= 1.5:
        label = f'🔥 {ratio}x'
    elif ratio >= 1.2:
        label = f'⚡ {ratio}x'
    else:
        label = f'{ratio}x'
    return ratio, label


def sector_trend(avg_daily, avg_weekly, avg_monthly):
    """Sector overall trend — mirrors AppScript updateSectorTrends logic"""
    if avg_daily > 0 and avg_weekly > 0 and avg_monthly > 0:
        return '🟢 BULL'
    if avg_daily < 0 and avg_weekly < 0 and avg_monthly < 0:
        return '🔴 BEAR'
    if avg_daily > 0.5 and avg_weekly > 1:
        return '🟢 BULL'
    if avg_daily < -0.5 and avg_weekly < -1:
        return '🔴 BEAR'
    return '⚪ NEUTRAL'
