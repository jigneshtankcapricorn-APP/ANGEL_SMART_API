import streamlit as st

st.set_page_config(
    page_title="Login – Angel One Trading",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── init ──────────────────────────────────────────────────────────
if "app_authenticated" not in st.session_state:
    st.session_state.app_authenticated = False

if st.session_state.app_authenticated:
    st.success("✅ Already logged in!")
    st.page_link("pages/1_Dashboard.py", label="Go to Dashboard →", icon="📊")
    st.stop()

# ── UI ────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { display: none; }
.login-box {
    max-width: 420px; margin: 60px auto;
    background: #fff; border-radius: 16px;
    padding: 40px 36px;
    box-shadow: 0 4px 30px rgba(0,0,0,0.10);
}
.login-title {
    text-align: center;
    font-size: 1.7rem;
    font-weight: 700;
    color: #1A73E8;
    margin-bottom: 6px;
}
.login-sub {
    text-align: center;
    color: #666;
    margin-bottom: 28px;
    font-size: 0.92rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="login-box">', unsafe_allow_html=True)
st.markdown('<div class="login-title">🔐 Angel One Trading</div>', unsafe_allow_html=True)
st.markdown('<div class="login-sub">Enter your credentials to continue</div>', unsafe_allow_html=True)

username = st.text_input("👤 Username", placeholder="Enter username")
password = st.text_input("🔑 Password", type="password", placeholder="Enter password")

login_btn = st.button("Login →", use_container_width=True, type="primary")

if login_btn:
    try:
        valid_user = st.secrets["APP_USERNAME"]
        valid_pass = st.secrets["APP_PASSWORD"]
    except KeyError:
        st.error("⚠️ APP_USERNAME / APP_PASSWORD not set in Streamlit Secrets.")
        st.info("Go to **App Settings → Secrets** and add:\n```\nAPP_USERNAME = \"yourname\"\nAPP_PASSWORD = \"yourpass\"\n```")
        st.stop()

    if username == valid_user and password == valid_pass:
        st.session_state.app_authenticated = True
        st.success("✅ Login successful! Redirecting…")
        st.switch_page("pages/1_Dashboard.py")
    else:
        st.error("❌ Incorrect username or password.")

st.markdown('</div>', unsafe_allow_html=True)
