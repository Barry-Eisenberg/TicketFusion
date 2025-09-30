import streamlit as st
import pandas as pd
from datetime import datetime
from check_account_availability import (
    load_accounts_from_sheet,
    load_orders_from_db,
    check_email_availability,
)
from db import get_engine

def run_availability_app():
    """Run the Account Availability Checker app"""
    
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
                st.error(f"Failed to read CSV: {e}")
                return
            
            # Use 'email' column if present, otherwise use first column
            if "email" in df_acc.columns:
                email_col = "email"
            else:
                email_col = df_acc.columns[0]
                
            emails = df_acc[email_col].dropna().astype(str).str.strip().tolist()
            st.info(f"Using {len(emails)} emails from uploaded CSV (column: {email_col})")
        else:
            # Load accounts from Google Sheets
            if not doc_id:
                st.warning("Please provide a Google Sheets DOC_ID or upload a CSV file.")
                return
                
            try:
                df_acc = load_accounts_from_sheet(doc_id, accounts_tab)
                if df_acc is None or df_acc.empty:
                    st.warning(f"No accounts found in Google Sheets tab '{accounts_tab}'")
                    return
                    
                # Use 'email' column if present, otherwise use first column
                if "email" in df_acc.columns:
                    email_col = "email"
                else:
                    email_col = df_acc.columns[0]
                    
                emails = df_acc[email_col].dropna().astype(str).str.strip().tolist()
                st.info(f"Using {len(emails)} emails from Google Sheets tab '{accounts_tab}' (column: {email_col})")
            except Exception as e:
                st.error(f"Failed to load accounts from Google Sheets: {e}")
                return

        # Load existing orders from database
        try:
            engine = get_engine()
            existing_orders = load_orders_from_db(engine)
            if existing_orders is None:
                existing_orders = pd.DataFrame()
        except Exception as e:
            st.error(f"Failed to load existing orders: {e}")
            return

        # Check availability for each email
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, email in enumerate(emails):
            status_text.text(f"Checking {i+1}/{len(emails)}: {email}")
            progress_bar.progress((i + 1) / len(emails))
            
            is_available, reason = check_email_availability(
                email=email,
                event=event,
                theater=theater,
                event_date=event_date,
                sold_date=sold_date,
                cnt=cnt,
                existing_orders=existing_orders
            )
            
            results.append({
                "email": email,
                "available": is_available,
                "reason": reason,
                "event": event,
                "theater": theater,
                "event_date": event_date,
                "cnt": cnt
            })
        
        status_text.text("Check completed!")
        
        # Display results
        results_df = pd.DataFrame(results)
        
        # Summary statistics
        available_count = results_df["available"].sum()
        total_count = len(results_df)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Checked", total_count)
        with col2:
            st.metric("Available", available_count)
        with col3:
            st.metric("Unavailable", total_count - available_count)
        
        # Results table
        st.subheader("Detailed Results")
        
        # Color-code the results
        def highlight_availability(row):
            if row["available"]:
                return ["background-color: #d4edda"] * len(row)
            else:
                return ["background-color: #f8d7da"] * len(row)
        
        styled_df = results_df.style.apply(highlight_availability, axis=1)
        st.dataframe(styled_df, use_container_width=True)
        
        # Download results
        csv = results_df.to_csv(index=False)
        st.download_button(
            label="Download Results as CSV",
            data=csv,
            file_name=f"availability_check_{today.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )