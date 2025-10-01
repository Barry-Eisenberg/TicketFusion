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
                                    # Import and run the ingest function
                                    import subprocess
                                    import sys
                                    
                                    # Try to run ingest.py as a subprocess
                                    result = subprocess.run([sys.executable, "ingest.py"], 
                                                          capture_output=True, text=True, cwd=".")
                                    
                                    if result.returncode == 0:
                                        st.success("✅ Data loaded successfully from Google Sheets!")
                                        st.rerun()  # Refresh the page to show new data
                                    else:
                                        st.error("❌ Failed to load data from Google Sheets")
                                        st.code(result.stderr)
                                        
                            except Exception as e:
                                st.error(f"❌ Error loading data: {str(e)}")
                
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
