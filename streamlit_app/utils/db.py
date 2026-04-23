"""
db.py — Database connection utility
------------------------------------
Provides a single shared DuckDB connection for the Streamlit app.
All pages import get_connection() from here rather than managing
their own connections, ensuring the same .db file is used throughout.

DuckDB is an embedded database — there's no server, just a file.
The connection is cached with st.cache_resource so Streamlit only
opens it once per session, not on every rerun.
"""

import duckdb
import streamlit as st
import os

DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "poker.db")


@st.cache_resource
def get_connection():
    """
    Open and cache a single DuckDB connection for the app lifetime.

    st.cache_resource is Streamlit's way of caching things that should
    be created once and shared — database connections, ML models, etc.
    Without this, a new connection would be opened on every rerun.
    """
    conn = duckdb.connect(DB_PATH)
    return conn


def fetch_all(query: str, params: list = None):
    """
    Run a SELECT query and return all rows as a list of dicts.
    Using dicts (via .df()) makes downstream Streamlit rendering easier.
    """
    conn = get_connection()
    if params:
        return conn.execute(query, params).df()
    return conn.execute(query).df()


def execute(query: str, params: list = None):
    """
    Run an INSERT / UPDATE / DELETE statement.
    All data-writing operations go through here.
    """
    conn = get_connection()
    if params:
        conn.execute(query, params)
    else:
        conn.execute(query)
