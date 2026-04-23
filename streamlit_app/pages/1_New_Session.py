"""
1_New_Session.py — Create a new playing session
-------------------------------------------------
This page demonstrates the core Streamlit pattern:
    1. Define a form with st.form()
    2. Widgets inside the form don't trigger reruns on change
    3. The script only reruns when the submit button is clicked
    4. On submit, validate inputs and write to DuckDB

The number prefix (1_) controls sidebar ordering.
The underscore-separated name becomes the page title.
"""

import streamlit as st
import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from utils.db import execute, fetch_all

st.set_page_config(page_title="New Session", page_icon="🃏", layout="centered")

st.title("New Session")
st.caption("Set the stakes and details for your playing session. "
           "These values will be used as defaults when logging hands.")

# ── Session form ─────────────────────────────────────────────────────────────
# st.form() groups all widgets into a single submission unit.
# Nothing is written to the database until the user clicks "Start Session".

with st.form("new_session_form", clear_on_submit=True):

    col1, col2 = st.columns(2)

    with col1:
        session_date = st.date_input(
            "Date",
            value=date.today(),
            format="MM/DD/YYYY",
            help="Date of the session"
        )
        location = st.text_input(
            "Location",
            placeholder="e.g. Aria, Home Game",
            help="Where you played"
        )
        game_type = st.selectbox(
            "Game type",
            options=["NLH"],
            help="No-Limit Hold'em (more formats can be added later)"
        )

    with col2:
        small_blind = st.number_input(
            "Small blind ($)",
            min_value=1,
            value=1,
            step=1,
            format="%d"
        )
        big_blind = st.number_input(
            "Big blind ($)",
            min_value=1,
            value=2,
            step=1,
            format="%d"
        )
        straddle = st.number_input(
            "Straddle ($)",
            min_value=0,
            value=0,
            step=1,
            format="%d",
            help="Set to 0 if there is no mandatory straddle"
        )
        default_stack = st.number_input(
            "Default buy-in / stack ($)",
            min_value=1,
            value=200,
            step=10,
            format="%d",
            help="Used to pre-fill stack sizes when logging hands"
        )

    notes = st.text_area(
        "Session notes",
        placeholder="Optional — table conditions, reads, anything worth remembering.",
        height=80,
    )

    submitted = st.form_submit_button("▶ Start Session", use_container_width=True)

# ── Handle submission ─────────────────────────────────────────────────────────
# Validation and DB write happen outside the form block but are only
# triggered when submitted = True (i.e. the button was clicked).

if submitted:
    # Basic validation
    errors = []
    if big_blind <= small_blind:
        errors.append("Big blind must be greater than small blind.")
    if straddle > 0 and straddle <= big_blind:
        errors.append("Straddle must be greater than the big blind.")

    if errors:
        for err in errors:
            st.error(err)
    else:
        straddle_value = straddle if straddle > 0 else None

        # Build a readable stakes label for display (e.g. "$1/$2" or "$2/$5/$10")
        if straddle_value:
            stakes_label = f"${small_blind:g}/${big_blind:g}/${straddle_value:g}"
        else:
            stakes_label = f"${small_blind:g}/${big_blind:g}"

        try:
            execute(
                """
                INSERT INTO sessions
                    (game_type, small_blind, big_blind, straddle,
                     date, location, default_stack, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    game_type,
                    small_blind,
                    big_blind,
                    straddle_value,
                    session_date,
                    location or None,
                    default_stack,
                    notes or None,
                ],
            )

            # Store the new session context in session_state so the
            # Log Hand page can pick it up without the user reselecting.
            # st.session_state persists across page navigation.
            sessions_df = fetch_all(
                """
                SELECT session_id, date, location, small_blind, big_blind, straddle, default_stack
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            if not sessions_df.empty:
                st.session_state["active_session"] = sessions_df.iloc[0].to_dict()

            st.success(
                f"✅ Session started — {stakes_label} "
                f"{'@ ' + location if location else ''} on {session_date}"
            )
            st.info("👈 Head to **Log Hand** in the sidebar to start recording hands.")

        except Exception as e:
            st.error(f"Database error: {e}")

# ── Recent sessions ───────────────────────────────────────────────────────────
# Show a read-only table of past sessions so the user can see what's logged.
# fetch_all returns a pandas DataFrame which st.dataframe renders natively.

st.divider()
st.subheader("Recent sessions")

try:
    recent = fetch_all(
        """
        SELECT
            date,
            CASE
                WHEN straddle IS NOT NULL
                THEN '$' || CAST(small_blind AS VARCHAR) || '/$' || CAST(big_blind AS VARCHAR)
                     || '/$' || CAST(straddle AS VARCHAR)
                ELSE '$' || CAST(small_blind AS VARCHAR) || '/$' || CAST(big_blind AS VARCHAR)
            END AS stakes,
            location,
            default_stack AS buy_in
        FROM sessions
        ORDER BY created_at DESC
        LIMIT 10
        """
    )
    if recent.empty:
        st.caption("No sessions logged yet.")
    else:
        st.dataframe(recent, use_container_width=True, hide_index=True)
except Exception:
    st.caption("No sessions found — run scripts/init_db.py to initialise the database.")