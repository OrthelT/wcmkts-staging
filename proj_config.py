import streamlit as st
import pathlib

# DB Auth Tokens
mkt_url = st.secrets["NEW_TURSO_DATABASE_URL"]
mkt_auth_token = st.secrets["NEW_TURSO_AUTH_TOKEN"]

sde_url = st.secrets["NEW_SDE_URL"]
sde_auth_token = st.secrets["NEW_SDE_AUTH_TOKEN"]

# Local DB Info
local_mkt_url = "sqlite+libsql:///wcmkt2.db"  # Changed to standard SQLite format for local dev
local_sde_url = "sqlite+libsql:///sde2.db"    # Changed to standard SQLite format for local dev
build_cost_url = "sqlite+libsql:///build_cost.db"
local_mkt_path = pathlib.Path("wcmkt2.db")
local_sde_path = pathlib.Path("sde2.db")
local_build_cost_path = pathlib.Path("build_cost.db")