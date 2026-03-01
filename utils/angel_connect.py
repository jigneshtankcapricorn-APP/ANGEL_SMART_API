"""
angel_connect.py
Angel One SmartAPI connection helpers.
"""
import streamlit as st
from SmartApi import SmartConnect
import pyotp
import requests
import pandas as pd
import time


# ──────────────────────────────────────────────────────────────────
# Instrument Master
# ──────────────────────────────────────────────────────────────────

INSTRUMENT_URL = (
    "https://margincalculator.angelbroking.com/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)

@st.cache_data(ttl=21600, show_spinner="📥 Loading instrument master...")
def load_instrument_master():
    """
    Fetch Angel One instrument master (cached 6 hours).
    Returns DataFrame with columns: symbol, token, exch_seg, name
    """
    try:
        resp = requests.get(INSTRUMENT_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        nse = df[df['exch_seg'] == 'NSE'].copy()
        # Clean symbol: "RELIANCE-EQ" → "RELIANCE"
        nse['sym_clean'] = (
            nse['symbol']
            .str.replace('-EQ', '', regex=False)
            .str.replace('-BE', '', regex=False)
            .str.strip()
        )
        return nse[['sym_clean', 'symbol', 'token', 'name', 'exch_seg',
                     'instrumenttype', 'lotsize']].copy()
    except Exception as e:
        st.error(f"❌ Instrument master load failed: {e}")
        return pd.DataFrame(columns=['sym_clean', 'symbol', 'token', 'name',
                                     'exch_seg', 'instrumenttype', 'lotsize'])


def get_token(instruments_df: pd.DataFrame, nse_symbol: str):
    """
    Map 'NSE:RELIANCE' → Angel One numeric token string.
    Returns token string or None.
    """
    sym = nse_symbol.replace('NSE:', '').strip()
    # 1. Exact sym_clean match
    row = instruments_df[instruments_df['sym_clean'] == sym]
    if not row.empty:
        return str(row.iloc[0]['token'])
    # 2. With -EQ suffix
    row = instruments_df[instruments_df['symbol'] == f"{sym}-EQ"]
    if not row.empty:
        return str(row.iloc[0]['token'])
    # 3. Name match
    row = instruments_df[instruments_df['name'] == sym]
    if not row.empty:
        return str(row.iloc[0]['token'])
    return None


# ──────────────────────────────────────────────────────────────────
# Index Tokens (hardcoded — Angel One standard tokens)
# ──────────────────────────────────────────────────────────────────
INDEX_TOKENS = {
    'Nifty 50':   {'token': '99926000', 'exchange': 'NSE', 'symbol': 'Nifty 50'},
    'Bank Nifty': {'token': '99926009', 'exchange': 'NSE', 'symbol': 'Nifty Bank'},
    'Nifty 500':  {'token': '99926012', 'exchange': 'NSE', 'symbol': 'Nifty 500'},
}


# ──────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────

def connect_angel_one():
    """
    Connect to Angel One SmartAPI using credentials from st.secrets.
    Returns (SmartConnect obj, user_data dict) or (None, None) on failure.
    """
    try:
        api_key   = st.secrets["API_KEY"]
        client_id = st.secrets["CLIENT_ID"]
        password  = st.secrets["PASSWORD"]
        totp_key  = st.secrets["TOTP_KEY"]

        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_key).now()
        data = obj.generateSession(client_id, password, totp)

        if data.get('status'):
            return obj, data.get('data', {})
        else:
            st.error(f"❌ Login failed: {data.get('message', 'Unknown error')}")
            return None, None
    except KeyError as e:
        st.error(f"❌ Missing secret: {e}. Check Streamlit Secrets settings.")
        return None, None
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        return None, None


# ──────────────────────────────────────────────────────────────────
# Data Fetching
# ──────────────────────────────────────────────────────────────────

def fetch_historical_ohlc(obj: SmartConnect, token: str,
                           exchange: str = 'NSE', days: int = 40):
    """
    Fetch daily OHLC from Angel One historical API.
    Returns list of dicts: {date, open, high, low, close, volume}
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
            return []
        ohlc = []
        for c in resp['data']:
            # c = [timestamp, open, high, low, close, volume]
            try:
                ohlc.append({
                    'date':   str(c[0])[:10],
                    'open':   float(c[1]),
                    'high':   float(c[2]),
                    'low':    float(c[3]),
                    'close':  float(c[4]),
                    'volume': int(c[5]),
                })
            except (IndexError, ValueError):
                pass
        # Last 30 candles only
        return ohlc[-30:] if len(ohlc) > 30 else ohlc
    except Exception:
        return []


def fetch_ltp(obj: SmartConnect, exchange: str, trading_symbol: str,
              token: str):
    """Fetch live LTP for a single instrument."""
    try:
        resp = obj.ltpData(exchange, trading_symbol, token)
        if resp and resp.get('data'):
            return resp['data'].get('ltp', 0)
    except Exception:
        pass
    return None


def fetch_quote(obj: SmartConnect, exchange: str, trading_symbol: str,
                token: str):
    """Fetch full quote (ltp, open, high, low, close, volume)."""
    try:
        resp = obj.ltpData(exchange, trading_symbol, token)
        if resp and resp.get('data'):
            return resp['data']
    except Exception:
        pass
    return {}


def fetch_index_data(obj: SmartConnect, index_name: str):
    """
    Fetch live price for index (Nifty 50, Bank Nifty, Nifty 500).
    Returns dict with ltp and prev_close.
    """
    info = INDEX_TOKENS.get(index_name)
    if not info:
        return {}
    try:
        resp = obj.ltpData(info['exchange'], info['symbol'], info['token'])
        if resp and resp.get('data'):
            return resp['data']
    except Exception:
        pass
    return {}


def fetch_index_history(obj: SmartConnect, index_name: str, days: int = 45):
    """Fetch historical OHLC for an index."""
    info = INDEX_TOKENS.get(index_name)
    if not info:
        return []
    return fetch_historical_ohlc(obj, info['token'], info['exchange'], days)
