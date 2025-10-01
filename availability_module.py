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
    
    # Load existing events/theaters - check session state first, then database
    existing_theaters = []
    existing_events = []
    
    if st.session_state.get('data_loaded', False) and 'sheet_data' in st.session_state:
        # Use session state data
        orders_preview = st.session_state['sheet_data'].copy()
        if orders_preview is not None and not orders_preview.empty:
            # Use original column names from Google Sheets
            theater_col = 'Theater' if 'Theater' in orders_preview.columns else 'theater'
            event_col = 'Event' if 'Event' in orders_preview.columns else 'event'
            
            if theater_col in orders_preview.columns:
                existing_theaters = sorted(pd.Series(orders_preview[theater_col]).dropna().astype(str).str.strip().unique().tolist())
            if event_col in orders_preview.columns:
                existing_events = sorted(pd.Series(orders_preview[event_col]).dropna().astype(str).str.strip().unique().tolist())
        st.sidebar.success("✅ Using data from Google Sheets")
    else:
        # Use database data
        engine_preview = get_engine()
        orders_preview = load_orders_from_db(engine_preview)
        if orders_preview is not None and not orders_preview.empty:
            existing_theaters = sorted(pd.Series(orders_preview.get("theater", [])).dropna().astype(str).str.strip().unique().tolist())
            existing_events = sorted(pd.Series(orders_preview.get("event", [])).dropna().astype(str).str.strip().unique().tolist())
        st.sidebar.info("📊 Using database data")

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
                st.stop()
        else:
            if not doc_id:
                st.warning("No Google Sheets DOC_ID provided and no CSV uploaded.")
                st.stop()
            df_acc = load_accounts_from_sheet(doc_id, accounts_tab)
            if df_acc is None:
                st.error("Failed to load accounts from Google Sheets.")
                st.stop()

        # Orders source: session state first, then database
        if st.session_state.get('data_loaded', False) and 'sheet_data' in st.session_state:
            # Use session state data for orders
            orders_df = st.session_state['sheet_data'].copy()
            
            # Rename columns to match expected database column names
            column_mapping = {
                'Sold Date': 'sold_date',
                'Event Date': 'event_date', 
                'Event': 'event',
                'Theater': 'theater',
                'Email': 'email',
                'CNT': 'cnt'
            }
            
            for old_col, new_col in column_mapping.items():
                if old_col in orders_df.columns:
                    orders_df = orders_df.rename(columns={old_col: new_col})
            
            # Convert date columns
            try:
                if 'sold_date' in orders_df.columns:
                    orders_df['sold_date'] = pd.to_datetime(orders_df['sold_date'], errors='coerce')
                if 'event_date' in orders_df.columns:
                    orders_df['event_date'] = pd.to_datetime(orders_df['event_date'], errors='coerce')
                if 'cnt' in orders_df.columns:
                    orders_df['cnt'] = pd.to_numeric(orders_df['cnt'], errors='coerce')
            except Exception as e:
                st.warning(f"Data conversion issues: {e}")
                
            st.info("✅ Using Google Sheets data for orders analysis")
        else:
            # Use database data
            engine = get_engine()
            orders_df = load_orders_from_db(engine)
            if orders_df is None or orders_df.empty:
                st.error("No orders data found in database.")
                st.stop()
            st.info("📊 Using database data for orders analysis")

        # Run the availability check
        result_df = check_email_availability(
            accounts_df=df_acc,
            orders_df=orders_df,
            prospective_event=event,
            prospective_theater=theater,
            prospective_event_date=pd.Timestamp(event_date),
            prospective_cnt=cnt,
            prospective_sold_date=pd.Timestamp(sold_date),
        )

        if result_df is not None and not result_df.empty:
            st.success(f"✅ Found {len(result_df)} available accounts!")
            
            # Display results
            st.subheader("Available Accounts")
            st.dataframe(result_df)
            
            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Available Accounts", len(result_df))
            with col2:
                if 'total_cnt' in result_df.columns:
                    avg_tickets = result_df['total_cnt'].mean()
                    st.metric("Avg Tickets/Account", f"{avg_tickets:.1f}")
            with col3:
                if 'last_purchase_days_ago' in result_df.columns:
                    avg_days = result_df['last_purchase_days_ago'].mean()
                    st.metric("Avg Days Since Last Purchase", f"{avg_days:.0f}")
            
            # Download option
            csv = result_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name=f"available_accounts_{event}_{event_date}.csv",
                mime="text/csv"
            )
        else:
            st.warning("⚠️ No available accounts found matching your criteria.")
            
        # Show some debug info
        with st.expander("🔍 Debug Information"):
            st.write(f"**Accounts loaded:** {len(df_acc) if df_acc is not None else 0}")
            st.write(f"**Orders loaded:** {len(orders_df) if orders_df is not None else 0}")
            st.write(f"**Search criteria:**")
            st.write(f"- Event: {event}")
            st.write(f"- Theater: {theater}")
            st.write(f"- Event Date: {event_date}")
            st.write(f"- Ticket Count: {cnt}")
            st.write(f"- Sold Date: {sold_date}")
            
            if orders_df is not None and not orders_df.empty:
                st.write("**Orders data sample:**")
                st.dataframe(orders_df.head())
