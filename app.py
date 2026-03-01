import streamlit as st
from smartapi import SmartConnect
import pyotp

st.set_page_config(page_title="Angel Mobile", layout="centered")
st.title("🚀 Angel One Mobile Scanner")

# LOGIN BUTTON
if st.button("🔴 CONNECT TO ANGEL ONE"):
    try:
        # Load keys from Secure Cloud Storage
        api_key = st.secrets["API_KEY"]
        client_id = st.secrets["CLIENT_ID"]
        password = st.secrets["PASSWORD"]
        totp_key = st.secrets["TOTP_KEY"]

        # Connect
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_key).now()
        data = obj.generateSession(client_id, password, totp)
        
        if data['status']:
            st.success(f"✅ Login Successful! User: {data['data']['clientName']}")
            
            # Fetch Price
            ltp = obj.ltpData("NSE", "SBIN-EQ", "3045")
            price = ltp['data']['ltp']
            st.metric(label="SBI LIVE PRICE", value=f"₹ {price}")
            
        else:
            st.error(f"Login Failed: {data['message']}")

    except Exception as e:
        st.error(f"Error: {e}")
