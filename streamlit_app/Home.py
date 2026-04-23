"""
Home.py — Home page
-------------------
This is the entry point Streamlit loads first.
Run the app from the repo root with:

    streamlit run streamlit_app/Home.py

The sidebar navigation to other pages is automatic — Streamlit
detects the pages/ folder and lists them in order.
"""

import streamlit as st
import sys
import os
from utils.db import fetch_all

sys.path.append(os.path.dirname(__file__))


st.set_page_config(
    page_title="Poker Analytics",
    page_icon="🃏",
    layout="wide"
)

st.title("🃏 Poker Analytics")
st.caption("Track, review, and analyze your live poker hands.")

st.divider()

col1, col2, col3 = st.columns(3)

try:
    sessions_df = fetch_all("SELECT COUNT(*) AS n FROM sessions")
    hands_df = fetch_all("SELECT COUNT(*) AS n FROM hands")
    result_df = fetch_all(
        "SELECT COALESCE(SUM(hero_result), 0) AS total FROM hands")

    with col1:
        st.metric("Sessions logged", int(sessions_df["n"].iloc[0]))
    with col2:
        st.metric("Hands logged", int(hands_df["n"].iloc[0]))
    with col3:
        total = float(result_df["total"].iloc[0])
        st.metric(
            "Total result",
            f"${total:,.2f}",
            delta=f"${total:,.2f}",
            delta_color="normal",
        )
except Exception:
    with col1:
        st.metric("Sessions logged", 0)
    with col2:
        st.metric("Hands logged", 0)
    with col3:
        st.metric("Total result", "$0.00")

st.divider()

# Navigation
st.subheader("Get started")
st.markdown("""
- **New Session** > Start a new playing and set your stakes
- **Log Hand** > Record a hand from your current session
- **Review Hands** > Filter and browse your hand history *(coming soon)*
""")

st.info("👈 Use the sidebar to navigate between pages.", icon="ℹ️")
