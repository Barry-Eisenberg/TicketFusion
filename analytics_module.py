import streamlit as st
import pandas as pd
import os
from sqlalchemy import create_engine, inspect
from pathlib import Path
from dotenv import load_dotenv

def run_analytics_app():
    """Run the Google Sheets Analytics app"""
    
    st.title("📊 Google Sheets Analytics")

    # Define your real schema mapping here.
    SCHEMA_MAP = {
        "Sold Date": ("sold_date", "datetime64[ns]"),
        "Event Date": ("event_date", "datetime64[ns]"),
        "Time": ("time", "string"),
        "Site": ("site", "string"),
        "Order ID": ("order_id", "Int64"),
        "Confirm ID": ("confirm_id", "string"),
        "Revenue": ("revenue", "float"),
        "Cost": ("cost", "float"),
        "CNT": ("cnt", "Int64"),
        "CC": ("cc", "string"),
        "Purch By": ("purch_by", "string"),
        "Purch Date": ("purch_date", "datetime64[ns]"),
        "Trans By": ("trans_by", "string"),
        "Trans Date": ("trans_date", "datetime64[ns]"),
        "Email": ("email", "string"),
        "Event": ("event", "string"),
        "Theater": ("theater", "string"),
        "Section": ("section", "string"),
        "Row": ("row", "string"),
        "Venue": ("venue", "string"),
        "Notes": ("notes", "string"),
    }

    # Check if we have session state data first (for cloud deployment)
    if st.session_state.get('data_loaded', False) and 'sheet_data' in st.session_state:
        st.success("✅ Using data loaded from Google Sheets")
        df = st.session_state['sheet_data'].copy()
        
        # Show last updated time
        if 'last_updated' in st.session_state:
            st.caption(f"Data last updated: {st.session_state['last_updated'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Rename columns to match expected database column names for consistency
        column_mapping = {}
        for sheet_col, (db_col, dtype) in SCHEMA_MAP.items():
            if sheet_col in df.columns:
                column_mapping[sheet_col] = db_col
        
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        # Basic data type conversion for session state data
        try:
            if 'sold_date' in df.columns:
                df['sold_date'] = pd.to_datetime(df['sold_date'], errors='coerce')
            if 'event_date' in df.columns:
                df['event_date'] = pd.to_datetime(df['event_date'], errors='coerce')
            if 'revenue' in df.columns:
                df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
            if 'cost' in df.columns:
                df['cost'] = pd.to_numeric(df['cost'], errors='coerce')
            if 'cnt' in df.columns:
                df['cnt'] = pd.to_numeric(df['cnt'], errors='coerce')
        except Exception as e:
            st.warning(f"Note: Some data conversion issues: {e}")
            
        st.info(f"📊 Showing {len(df)} rows from Google Sheets data")
        
    else:
        # Fallback to database (for local development)
        BASE_DIR = Path(__file__).resolve().parent
        load_dotenv(BASE_DIR / ".env")
        
        DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data.db'}")
        engine = create_engine(DB_URL, future=True)

        # PRAGMA tuning for SQLite
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")

        st.caption(f"Using database: {DB_URL}")

        # Optional: fail early with a clear message if the table isn't there
        inspector = inspect(engine)
        if "sheet_facts" not in inspector.get_table_names():
            st.error("Table 'sheet_facts' not found in this database. Make sure ingest.py wrote to the same DB_URL shown above.")
            st.info("💡 Try using the 'Load Data from Google Sheets' button on the main page.")
            st.stop()

        @st.cache_data(ttl=60)
        def load_data_from_db():
            """Load data from database (for local development)"""
            inspector = inspect(engine)
            table_cols = [c["name"] for c in inspector.get_columns("sheet_facts")]
            desired = ["row_hash", "ingested_at"] + [dst for _, (dst, _) in SCHEMA_MAP.items()]
            cols = [c for c in desired if c in table_cols]
            if not cols:
                return pd.DataFrame(columns=desired)
            cols_sql = ", ".join(cols)
            df = pd.read_sql(f"SELECT {cols_sql} FROM sheet_facts ORDER BY ingested_at DESC LIMIT 100000", engine)

            # Coerce dtypes based on SCHEMA_MAP
            dst_dtype = {dst: dtype for _, (dst, dtype) in SCHEMA_MAP.items()}
            for col, dtype in dst_dtype.items():
                if col not in df.columns:
                    continue
                try:
                    if dtype == "datetime64[ns]":
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    elif dtype == "Int64":
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                    elif dtype == "float":
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    else:
                        df[col] = df[col].astype("string")
                except Exception:
                    pass

            if "ingested_at" in df.columns:
                df["ingested_at"] = pd.to_datetime(df["ingested_at"], errors="coerce")

            return df

        df = load_data_from_db()
        st.info(f"📊 Showing {len(df)} rows from database")

    st.write(f"Rows loaded: {len(df)}")

    # Rest of the analytics code continues here...
    # (keeping the existing filtering and visualization code)
    
    # Filters
    st.markdown("---")
    st.subheader("Filters")
    
    # Show basic data info
    if not df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Rows", len(df))
            if 'revenue' in df.columns:
                total_revenue = df['revenue'].sum()
                st.metric("Total Revenue", f"${total_revenue:,.2f}")
        
        with col2:
            if 'event' in df.columns:
                unique_events = df['event'].nunique()
                st.metric("Unique Events", unique_events)
            if 'cnt' in df.columns:
                total_tickets = df['cnt'].sum()
                st.metric("Total Tickets", total_tickets)
        
        # Display sample data
        st.subheader("Sample Data")
        st.dataframe(df.head(10))
        
    else:
        st.warning("No data available. Please load data using the 'Load Data from Google Sheets' button on the main page.")
