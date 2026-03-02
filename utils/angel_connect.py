import streamlit as st
import requests
import pandas as pd

INSTRUMENT_URL = (
    "https://margincalculator.angelbroking.com/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)

INDEX_TOKENS = {
    'Nifty 50':   {'token': '99926000', 'exchange': 'NSE', 'symbol': 'Nifty 50'},
    'Bank Nifty': {'token': '99926009', 'exchange': 'NSE', 'symbol': 'Nifty Bank'},
    'Nifty 500':  {'token': '99926012', 'exchange': 'NSE', 'symbol': 'Nifty 500'},
}


@st.cache_data(ttl=21600, show_spinner="📥 Loading instruments…")
def load_instrument_master():
    try:
        resp = requests.get(INSTRUMENT_URL, timeout=30)
        resp.raise_for_status()
        df = pd.DataFrame(resp.json())
        nse = df[df['exch_seg'] == 'NSE'].copy()
        nse['sym_clean'] = (
            nse['symbol']
            .str.replace('-EQ', '', regex=False)
            .str.replace('-BE', '', regex=False)
            .str.strip()
        )
        return nse[['sym_clean', 'symbol', 'token', 'name', 'exch_seg']].copy()
    except Exception as e:
        return pd.DataFrame(columns=['sym_clean', 'symbol', 'token', 'name', 'exch_seg'])


def get_token(instruments_df, nse_symbol):
    sym = nse_symbol.replace('NSE:', '').strip()
    row = instruments_df[instruments_df['sym_clean'] == sym]
    if not row.empty:
        return str(row.iloc[0]['token'])
    row = instruments_df[instruments_df['symbol'] == f"{sym}-EQ"]
    if not row.empty:
        return str(row.iloc[0]['token'])
    return None


def connect_angel_one():
    # SmartApi imported LAZILY — only when user clicks connect
    try:
        from SmartApi import SmartConnect
        import pyotp

        api_key   = st.secrets["API_KEY"]
        client_id = st.secrets["CLIENT_ID"]
        password  = st.secrets["PASSWORD"]
        totp_key  = st.secrets["TOTP_KEY"]

        obj  = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_key).now()
        data = obj.generateSession(client_id, password, totp)

        if data.get('status'):
            return obj, data.get('data', {})
        st.error(f"❌ Login failed: {data.get('message', 'Unknown error')}")
        return None, None
    except KeyError as e:
        st.error(f"❌ Missing secret: {e}")
        return None, None
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return None, None


def fetch_historical_ohlc(obj, token, exchange='NSE', days=40):
    from datetime import datetime, timedelta
    end, start = datetime.now(), datetime.now() - timedelta(days=days)
    param = {
        "exchange": exchange, "symboltoken": token,
        "interval": "ONE_DAY",
        "fromdate": start.strftime("%Y-%m-%d 09:15"),
        "todate":   end.strftime("%Y-%m-%d 15:30"),
    }
    try:
        resp = obj.getCandleData(param)
        if not resp or not resp.get('data'):
            return []
        ohlc = []
        for c in resp['data']:
            try:
                ohlc.append({
                    'date': str(c[0])[:10],
                    'open': float(c[1]), 'high': float(c[2]),
                    'low':  float(c[3]), 'close': float(c[4]),
                    'volume': int(c[5])
                })
            except Exception:
                pass
        return ohlc[-30:] if len(ohlc) > 30 else ohlc
    except Exception:
        return []


def fetch_ltp(obj, exchange, trading_symbol, token):
    try:
        resp = obj.ltpData(exchange, trading_symbol, token)
        if resp and resp.get('data'):
            return resp['data'].get('ltp', 0)
    except Exception:
        pass
    return None


def fetch_index_data(obj, index_name):
    info = INDEX_TOKENS.get(index_name, {})
    if not info:
        return {}
    try:
        resp = obj.ltpData(info['exchange'], info['symbol'], info['token'])
        if resp and resp.get('data'):
            return resp['data']
    except Exception:
        pass
    return {}


def fetch_index_history(obj, index_name, days=45):
    info = INDEX_TOKENS.get(index_name, {})
    if not info:
        return []
    return fetch_historical_ohlc(obj, info['token'], info['exchange'], days)


def fetch_live_52w(obj, token, exchange='NSE', days=365):
    """
    Fetch 52W High, 52W Low, and 20-day avg volume LIVE from Angel One.
    Returns dict: {w52_high, w52_low, avg_vol_20d, ref_volume}
    """
    from datetime import datetime, timedelta
    end   = datetime.now()
    start = end - timedelta(days=days)
    param = {
        "exchange":    exchange,
        "symboltoken": token,
        "interval":    "ONE_DAY",
        "fromdate":    start.strftime("%Y-%m-%d 09:15"),
        "todate":      end.strftime("%Y-%m-%d 15:30"),
    }
    try:
        resp = obj.getCandleData(param)
        if not resp or not resp.get('data'):
            return {}
        candles = resp['data']
        highs  = [float(c[2]) for c in candles if c[2]]
        lows   = [float(c[3]) for c in candles if c[3]]
        vols   = [int(c[5])   for c in candles if c[5]]
        w52_high = round(max(highs), 2) if highs else 0
        w52_low  = round(min(lows),  2) if lows  else 0
        ref_vol  = vols[-1] if vols else 0
        avg_vol  = round(sum(vols[-20:]) / min(len(vols[-20:]), 20), 0) if vols else 0
        return {
            'w52_high':    w52_high,
            'w52_low':     w52_low,
            'ref_volume':  ref_vol,
            'avg_vol_20d': avg_vol,
        }
    except Exception:
        return {}


def refresh_session(obj, user_data):
    """
    Attempt to refresh an existing Angel One session token.
    Returns (new_obj, new_user_data) or (None, None) on failure.
    """
    try:
        from SmartApi import SmartConnect
        import pyotp
        import streamlit as st

        refresh_token = (user_data or {}).get("refreshToken", "")
        if not refresh_token:
            return connect_angel_one()

        api_key = st.secrets["API_KEY"]
        obj2 = SmartConnect(api_key=api_key)
        resp = obj2.generateToken(refresh_token)
        if resp and resp.get("status"):
            return obj2, resp.get("data", {})
    except Exception:
        pass
    # Fallback: full re-login
    return connect_angel_one()
