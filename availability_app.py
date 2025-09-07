import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from check_account_availability import (
    load_accounts_from_sheet,
    load_orders_from_db,
    check_email_availability,
)
from db import get_engine

st.set_page_config(page_title="Account Availability Checker", layout="wide")
st.title("Account Availability Checker")

st.sidebar.header("Prospective purchase")
# We'll load existing events/theaters from Orders to populate helpers.
engine_preview = get_engine()
orders_preview = load_orders_from_db(engine_preview)
existing_theaters = []
existing_events = []
if orders_preview is not None and not orders_preview.empty:
    existing_theaters = sorted(pd.Series(orders_preview.get("theater", [])).dropna().astype(str).str.strip().unique().tolist())
    existing_events = sorted(pd.Series(orders_preview.get("event", [])).dropna().astype(str).str.strip().unique().tolist())

# Theater dropdown (optional empty choice)
theater = st.sidebar.selectbox("Theater / Venue", options=[""] + existing_theaters, index=0)

# Event: allow selecting an existing event or typing a new one.
event_choice = st.sidebar.selectbox("Choose existing event or select 'Other' to type", options=(existing_events + ["Other"]))
if event_choice == "Other":
    event = st.sidebar.text_input("Event (type new)")
else:
    event = event_choice
event_date = st.sidebar.date_input("Event Date", value=datetime.utcnow().date())
cnt = st.sidebar.number_input("Ticket count (cnt)", min_value=1, max_value=100, value=1)
sold_date = st.sidebar.date_input("Sold Date", value=datetime.utcnow().date())

st.sidebar.header("Data sources")
doc_id = st.sidebar.text_input("Google Sheets DOC_ID (optional)")
accounts_tab = st.sidebar.text_input("Accounts tab name", value="Accounts")
accounts_csv_file = st.sidebar.file_uploader("Optional: upload Accounts CSV (uses 'email' column or first column)", type=["csv"])

if st.sidebar.button("Run check"):
    today = pd.Timestamp.utcnow()
    # Accounts source: CSV uploaded -> use it; otherwise use Google Sheets Accounts tab
    if accounts_csv_file is not None:
        try:
            df_acc = pd.read_csv(accounts_csv_file)
        except Exception as e:
            st.error(f"Failed to read uploaded CSV: {e}")
            st.stop()
        if "email" in df_acc.columns:
            emails = df_acc["email"].astype("string").dropna().str.strip().str.lower().drop_duplicates().reset_index(drop=True)
        else:
            emails = df_acc.iloc[:, 0].astype("string").dropna().str.strip().str.lower().drop_duplicates().reset_index(drop=True)
    else:
        try:
            emails = load_accounts_from_sheet(doc_id or None, accounts_tab)
        except Exception as e:
            st.error(f"Failed to load Accounts tab: {e}")
            st.stop()

    engine = get_engine()
    orders = load_orders_from_db(engine)

    available = []
    unavailable = {}
    ed_ts = pd.to_datetime(event_date)
    sd_ts = pd.to_datetime(sold_date)

    for e in emails:
        ok, reasons = check_email_availability(
            e,
            orders,
            today,
            event=event or None,
            theater=theater or None,
            event_date=ed_ts,
            cnt_new=int(cnt),
            sold_date_new=sd_ts,
        )
        if ok:
            available.append(e)
        else:
            unavailable[e] = reasons

    st.subheader("Results")
    st.write(f"Available: {len(available)} -- Unavailable: {len(unavailable)}")
    if available:
        st.multiselect("Available emails", available, default=available[:10])
    if unavailable:
        st.write("Unavailable (sample):")
        for e, reasons in list(unavailable.items())[:50]:
            st.write(f"- {e}")
            for r in reasons:
                st.write(f"    - {r}")
