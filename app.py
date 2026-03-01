import streamlit as st
from SmartApi import SmartConnect
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
            # ✅ FIXED: Safely get clientName (key name varies by API version)
            user_data = data.get('data', {})
            client_name = (
                user_data.get('clientName') or
                user_data.get('name') or
                user_data.get('client_name') or
                client_id  # fallback to client ID if name not found
            )

            st.success(f"✅ Login Successful! User: {client_name}")
            st.session_state['obj'] = obj  # Save session

            # Fetch SBI Live Price
            ltp = obj.ltpData("NSE", "SBIN-EQ", "3045")

            if ltp and ltp.get('data'):
                price = ltp['data']['ltp']
                st.metric(label="SBI LIVE PRICE", value=f"₹ {price}")
            else:
                st.warning("⚠️ Could not fetch live price. Check symbol/token.")

        else:
            st.error(f"❌ Login Failed: {data.get('message', 'Unknown error')}")

    except KeyError as e:
        st.error(f"❌ Missing secret key: {e} — Check your Streamlit Secrets settings")
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.info("💡 Debug info: Check your API_KEY, CLIENT_ID, PASSWORD, TOTP_KEY in secrets")
