"""
NSE Sector Index tokens for Angel One SmartAPI.
Fetches REAL daily/weekly/monthly % change from actual sector indices.
"""

# Verified Angel One sector index tokens (NSE)
SECTOR_INDICES = {
    "Nifty Bank":          {"token": "99926009", "exchange": "NSE", "symbol": "Nifty Bank"},
    "Nifty IT":            {"token": "99926048", "exchange": "NSE", "symbol": "Nifty IT"},
    "Nifty Pharma":        {"token": "99926045", "exchange": "NSE", "symbol": "Nifty Pharma"},
    "Nifty Auto":          {"token": "99926037", "exchange": "NSE", "symbol": "Nifty Auto"},
    "Nifty FMCG":          {"token": "99926038", "exchange": "NSE", "symbol": "Nifty FMCG"},
    "Nifty Metal":         {"token": "99926044", "exchange": "NSE", "symbol": "Nifty Metal"},
    "Nifty Realty":        {"token": "99926047", "exchange": "NSE", "symbol": "Nifty Realty"},
    "Nifty PSU Bank":      {"token": "99926046", "exchange": "NSE", "symbol": "Nifty PSU Bank"},
    "Nifty Energy":        {"token": "99926041", "exchange": "NSE", "symbol": "Nifty Energy"},
    "Nifty Infra":         {"token": "99926042", "exchange": "NSE", "symbol": "Nifty Infra"},
    "Nifty Media":         {"token": "99926043", "exchange": "NSE", "symbol": "Nifty Media"},
    "Nifty MNC":           {"token": "99926040", "exchange": "NSE", "symbol": "Nifty MNC"},
    "Nifty Financial Svcs":{"token": "99926049", "exchange": "NSE", "symbol": "Nifty Fin Service"},
    "Nifty Healthcare":    {"token": "99926050", "exchange": "NSE", "symbol": "Nifty Healthcare"},
    "Nifty Oil & Gas":     {"token": "99926055", "exchange": "NSE", "symbol": "Nifty Oil and Gas"},
    "Nifty Chemicals":     {"token": "99926058", "exchange": "NSE", "symbol": "Nifty Chemicals"},
    "Nifty CPSE":          {"token": "99926039", "exchange": "NSE", "symbol": "Nifty CPSE"},
    "Nifty Consumption":   {"token": "99926060", "exchange": "NSE", "symbol": "Nifty India Consumption"},
    "Nifty Mfg":           {"token": "99926056", "exchange": "NSE", "symbol": "Nifty India Mfg"},
    "Nifty Defence":       {"token": "99926061", "exchange": "NSE", "symbol": "Nifty India Defence"},
}


def fetch_sector_data(obj):
    """
    Fetch real OHLC for all sector indices.
    Returns list of dicts with Sector, Daily%, Weekly%, Monthly%, Trend.
    """
    from utils.angel_connect import fetch_historical_ohlc
    from utils.indicators import sector_trend

    results = []
    for sector_name, info in SECTOR_INDICES.items():
        try:
            hist = fetch_historical_ohlc(
                obj, info["token"], info["exchange"], days=45
            )
            if not hist or len(hist) < 6:
                continue

            ltp = hist[-1]["close"]
            d   = _pct(ltp, hist[-2]["close"]) if len(hist) >= 2  else 0.0
            w   = _pct(ltp, hist[-6]["close"]) if len(hist) >= 6  else 0.0
            m   = _pct(ltp, hist[-22]["close"]) if len(hist) >= 22 else 0.0

            results.append({
                "Sector":    sector_name,
                "LTP":       round(ltp, 2),
                "Daily %":   round(d, 2),
                "Weekly %":  round(w, 2),
                "Monthly %": round(m, 2),
                "Trend":     sector_trend(d, w, m),
                "_d":        d,
                "Source":    "live",
            })
        except Exception:
            continue

    return results


def _pct(new, old):
    if old and old != 0:
        return round((new - old) / old * 100, 2)
    return 0.0
