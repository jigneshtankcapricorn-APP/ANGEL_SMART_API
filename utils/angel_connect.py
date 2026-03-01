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
