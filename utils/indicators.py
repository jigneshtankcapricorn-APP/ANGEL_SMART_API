def calculate_atr(ohlc, period=10):
    tr_list = []
    for i in range(1, len(ohlc)):
        h, l, pc = ohlc[i]['high'], ohlc[i]['low'], ohlc[i-1]['close']
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = []
    for i in range(len(tr_list)):
        if i < period - 1:
            atr.append(None)
        elif i == period - 1:
            atr.append(sum(tr_list[:period]) / period)
        else:
            atr.append(((atr[i-1] * (period-1)) + tr_list[i]) / period)
    return atr


def calculate_supertrend_signals(ohlc, period=10, multiplier=3):
    result = {
        'supertrend_status': '🔴 RED', 'days_green': 0,
        'is_flat': False, 'swing_high': None,
        'swing_high_date': None, 'is_breakout': False, 'ema23': None
    }
    if not ohlc or len(ohlc) < 15:
        return result

    ltp = ohlc[-1]['close']
    atr = calculate_atr(ohlc, period)
    dirs, st_vals = [], []
    pfu, pfl, pst = 0.0, 0.0, 0.0

    for i in range(len(ohlc) - 1):
        a = atr[i]
        if a is None or i < period:
            dirs.append(None); st_vals.append(None); continue
        d = ohlc[i+1]
        hl = (d['high'] + d['low']) / 2
        bu, bl = hl + multiplier*a, hl - multiplier*a
        pc = ohlc[i]['close']
        fu = bu if (bu < pfu or pc > pfu) else pfu
        fl = bl if (bl > pfl or pc < pfl) else pfl
        if pst == pfu:
            st, dr = (fu, -1) if d['close'] <= fu else (fl, 1)
        else:
            st, dr = (fl, 1) if d['close'] >= fl else (fu, -1)
        dirs.append(dr); st_vals.append(st)
        pfu, pfl, pst = fu, fl, st

    last_dir = next((d for d in reversed(dirs) if d is not None), None)
    result['supertrend_status'] = '🟢 GREEN' if last_dir == 1 else '🔴 RED'

    days_green = 0
    for d in reversed(dirs):
        if d == 1: days_green += 1
        elif d == -1: break
    result['days_green'] = days_green

    trans = -1
    for i in range(1, len(dirs)):
        if dirs[i-1] == -1 and dirs[i] == 1:
            trans = i

    if trans != -1 and days_green >= 5:
        days_since = (len(ohlc)-1) - (trans+1)
        gi = trans + 1
        if 0 <= gi < len(ohlc):
            sh, sh_date = ohlc[gi]['high'], ohlc[gi].get('date', '')
            if days_since <= 7:
                start = max(0, len(ohlc) - days_green)
                for i in range(start, len(ohlc)-1):
                    if ohlc[i]['high'] > sh:
                        sh, sh_date = ohlc[i]['high'], ohlc[i].get('date', '')
            result['swing_high'] = round(sh, 2)
            result['swing_high_date'] = str(sh_date)[:10] if sh_date else None

    if days_green >= 5:
        start = max(0, len(st_vals) - days_green)
        vals = [v for v in st_vals[start:] if v is not None]
        if len(vals) >= 5:
            mn, mx = min(vals), max(vals)
            result['is_flat'] = ((mx - mn) / mn * 100) < 3.5 if mn > 0 else False

    if result['swing_high'] and days_green >= 5:
        lc = ohlc[-1]
        if ltp > result['swing_high'] and lc['close'] > lc['open']:
            result['is_breakout'] = True

    closes = [d['close'] for d in ohlc]
    if len(closes) >= 23:
        ep = 2 / 24
        ema = sum(closes[:23]) / 23
        for c in closes[23:]:
            ema = c * ep + ema * (1 - ep)
        result['ema23'] = round(ema, 2)

    return result


def compute_risk(ltp, ema23):
    sl5 = round(ltp * 0.95, 2)
    if ema23 and ema23 > 0:
        rec_sl = round(max(ema23, sl5), 2)
        risk_pct = round((ltp - ema23) / ltp * 100, 2)
    else:
        rec_sl = sl5
        risk_pct = 5.0
    if risk_pct > 7:   status = '⚠️ HIGH RISK'
    elif risk_pct > 5: status = '🟡 MODERATE'
    else:              status = '🟢 LOW RISK'
    return {'sl_5pct': sl5, 'recommended_sl': rec_sl,
            'risk_ema_pct': risk_pct, 'risk_status': status}


def compute_vol_ratio(volume, avg_vol):
    if not avg_vol or avg_vol == 0:
        return 0, '—'
    r = round(volume / avg_vol, 2)
    if r >= 1.5: return r, f'🔥 {r}x'
    if r >= 1.2: return r, f'⚡ {r}x'
    return r, f'{r}x'


def sector_trend(daily, weekly, monthly):
    if daily > 0 and weekly > 0 and monthly > 0: return '🟢 BULL'
    if daily < 0 and weekly < 0 and monthly < 0: return '🔴 BEAR'
    if daily > 0.5 and weekly > 1:               return '🟢 BULL'
    if daily < -0.5 and weekly < -1:             return '🔴 BEAR'
    return '⚪ NEUTRAL'
