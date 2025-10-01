import streamlit as st

# Configure the page
st.set_page_config(
    page_title="TicketFusion Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Main navigation
st.title("🎫 TicketFusion Dashboard")
st.markdown("---")

# Sidebar navigation
st.sidebar.title("Navigation")
app_choice = st.sidebar.selectbox(
    "Choose an application:",
    ["Home", "Google Sheets Analytics", "Account Availability Checker"]
)

if app_choice == "Home":
    st.markdown("""
    ## Welcome to TicketFusion! 🎫
    
    TicketFusion is a comprehensive ticket management and analytics platform that helps you:
    
    ### 📊 Google Sheets Analytics
    - Analyze ticket sales data from Google Sheets
    - View revenue trends and patterns
    - Monitor ingestion and data quality
    - Filter and explore your ticket data
    
    ### 🔍 Account Availability Checker
    - Check email availability for prospective purchases
    - Validate customer accounts against existing orders
    - Prevent duplicate bookings and conflicts
    - Streamline the ticket purchasing process
    
    **Getting Started:**
    1. Use the sidebar to navigate between applications
    2. Make sure your database is properly configured
    3. Upload your service account credentials if using Google Sheets
    
    **Need Help?**
    - Check the README.md for detailed setup instructions
    - Ensure your data.db file contains the necessary tables
    - Verify your Google Sheets credentials are properly configured
    """)
    
    # Quick system status
    st.markdown("---")
    st.subheader("System Status")
    
    # Check database connection and row count
    try:
        from db import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
            tables = [row[0] for row in result.fetchall()]
            
            # Check row count in sheet_facts
            row_count = 0
            if 'sheet_facts' in tables:
                result = conn.execute(text("SELECT COUNT(*) FROM sheet_facts"))
                row_count = result.fetchone()[0]
            
            if tables:
                st.success(f"✅ Database connected ({len(tables)} tables found)")
                if 'sheet_facts' in tables:
                    st.info(f"📊 Sheet facts table has {row_count} rows")
                    
                    # If we have very few rows, offer to load data
                    if row_count <= 5:
                        st.warning("⚠️ Very few data rows detected. You may want to load data from Google Sheets.")
                        
                        # Add a button to load data from Google Sheets
                        if st.button("🔄 Load Data from Google Sheets", help="This will import data from your configured Google Sheets document"):
                            try:
                                with st.spinner("Loading data from Google Sheets..."):
                                    # Load data directly into session state (for cloud deployment)
                                    import pandas as pd
                                    from datetime import datetime
                                    
                                    # Import the Google Sheets reading functionality
                                    import gspread
                                    from google.oauth2.service_account import Credentials
                                    import os
                                    
                                    # Get credentials
                                    if hasattr(st, 'secrets') and "google_service_account" in st.secrets:
                                        service_account_info = dict(st.secrets["google_service_account"])
                                        creds = Credentials.from_service_account_info(
                                            service_account_info, 
                                            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly", 
                                                   "https://www.googleapis.com/auth/drive.readonly"]
                                        )
                                    else:
                                        st.error("❌ Google service account credentials not found in secrets")
                                        st.stop()
                                    
                                    # Get document ID
                                    doc_id = st.secrets.get("GOOGLE_SHEETS_DOC_ID") if hasattr(st, 'secrets') else None
                                    if not doc_id:
                                        st.error("❌ Google Sheets document ID not found in secrets")
                                        st.stop()
                                    
                                    # Connect and read data
                                    gc = gspread.authorize(creds)
                                    sheet = gc.open_by_key(doc_id).worksheet("Orders")
                                    
                                    # Get all values and convert to DataFrame
                                    st.write("📥 Fetching all data from Google Sheets...")
                                    values = sheet.get_all_values()
                                    st.write(f"✅ Raw data fetched: {len(values)} total rows")
                                    
                                    if len(values) > 4:  # Skip header rows
                                        headers = values[3]  # Row 4 (index 3) contains headers
                                        data_rows = values[4:]  # Data starts from row 5
                                        st.write(f"📋 Headers: {len(headers)} columns")
                                        st.write(f"📊 Data rows available: {len(data_rows)}")
                                        
                                        # Create DataFrame
                                        df = pd.DataFrame(data_rows, columns=headers)
                                        st.write(f"📊 DataFrame created: {df.shape[0]} rows × {df.shape[1]} columns")
                                        
                                        # Filter out empty rows - step by step for debugging
                                        initial_count = len(df)
                                        df = df.dropna(how='all')
                                        after_dropna = len(df)
                                        st.write(f"🧹 After removing completely empty rows: {after_dropna} (removed {initial_count - after_dropna})")
                                        
                                        df = df[df['Event'].notna() & (df['Event'] != '')]
                                        final_count = len(df)
                                        st.write(f"🧹 After removing rows with empty Events: {final_count} (removed {after_dropna - final_count})")
                                        
                                        if not df.empty:
                                            # Show memory usage
                                            memory_usage = df.memory_usage(deep=True).sum() / 1024 / 1024  # MB
                                            st.write(f"💾 DataFrame memory usage: {memory_usage:.2f} MB")
                                            
                                            # Store in session state
                                            st.session_state['sheet_data'] = df
                                            st.session_state['data_loaded'] = True
                                            st.session_state['last_updated'] = datetime.now()
                                            
                                            st.success(f"✅ Data loaded successfully! {len(df)} rows imported from Google Sheets")
                                            
                                            # Verify session state storage
                                            stored_df = st.session_state.get('sheet_data')
                                            if stored_df is not None:
                                                st.write(f"✅ Verified in session state: {len(stored_df)} rows")
                                                st.write(f"📊 Sample events: {stored_df['Event'].head().tolist()}")
                                                st.write(f"📊 Unique events: {stored_df['Event'].nunique()}")
                                            else:
                                                st.error("❌ Failed to store data in session state")
                                            
                                            st.rerun()  # Refresh the page to show new data
                                        else:
                                            st.error("❌ No valid data found after filtering")
                                    else:
                                        st.error("❌ Not enough rows in Google Sheets")
                                        
                            except Exception as e:
                                st.error(f"❌ Error loading data: {str(e)}")
                                import traceback
                                st.text(traceback.format_exc())
                
                with st.expander("View Tables"):
                    for table in tables:
                        st.text(f"• {table}")
            else:
                st.warning("⚠️ Database connected but no tables found")
                
    except Exception as e:
        st.error(f"❌ Database connection failed: {str(e)}")

        # Check for service account
    import os
    from pathlib import Path
    service_account_path = Path("service_account.json")
    if service_account_path.exists():
        st.success("✅ Google Sheets service account found")
    else:
        st.warning("⚠️ service_account.json not found - Google Sheets features may not work")

elif app_choice == "Google Sheets Analytics":
    # Import and run the analytics app
    st.markdown("---")
    try:
        from analytics_module import run_analytics_app
        run_analytics_app()
    except ImportError as e:
        st.error(f"Import error: {str(e)}")
        st.markdown("Some required modules may not be available. Please check the deployment logs.")
    except Exception as e:
        st.error(f"Error loading Analytics app: {str(e)}")
        st.markdown("Make sure your database is properly configured and contains the 'sheet_facts' table.")
        
        # Show more detailed error information for debugging
        import traceback
        with st.expander("Debug Information"):
            st.code(traceback.format_exc())

elif app_choice == "Account Availability Checker":
    # Import and run the availability checker app
    st.markdown("---")
    try:
        from availability_module import run_availability_app
        run_availability_app()
    except ImportError as e:
        st.error(f"Import error: {str(e)}")
        st.markdown("Some required modules may not be available. Please check the deployment logs.")
    except Exception as e:
        st.error(f"Error loading Availability Checker: {str(e)}")
        st.markdown("Make sure your database is properly configured and your Google Sheets credentials are set up.")
        
        # Show more detailed error information for debugging
        import traceback
        with st.expander("Debug Information"):
            st.code(traceback.format_exc())
