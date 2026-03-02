"""
Persistent data store using st.cache_resource.
Data survives page navigation AND browser refresh (lives in server memory).
Clears only when Streamlit server restarts.
"""
import streamlit as st


@st.cache_resource
def _store():
    """Server-level store — persists across all reruns and page refreshes."""
    return {
        "watchlist_df":   None,
        "signals_df":     None,
        "signals_meta":   None,
        "sector_df":      None,
        "last_watchlist": None,   # timestamp string
        "last_signals":   None,
        "last_sector":    None,
    }


def save(key: str, value):
    _store()[key] = value


def load(key: str):
    return _store().get(key)


def clear(key: str):
    _store()[key] = None


def clear_all():
    s = _store()
    for k in list(s.keys()):
        s[k] = None
