import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re

# Configure the page
st.set_page_config(
    page_title="TicketFusion Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_google_sheets_data():
    """Load data from Google Sheets with proper error handling"""
    try:
        # Get credentials from Streamlit secrets
        credentials_dict = dict(st.secrets["google_service_account"])
        
        # Define the required scopes for Google Sheets
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Create credentials with proper scopes
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        
        # Connect to Google Sheets
        gc = gspread.authorize(credentials)
        
        # Open the sheet using the document ID from secrets
        doc_id = st.secrets["GOOGLE_SHEETS_DOC_ID"]
        sheet = gc.open_by_key(doc_id)
        
        # Get all worksheets
        worksheets = sheet.worksheets()
        
        # Load data from each worksheet
        data = {}
        for worksheet in worksheets:
            try:
                # First try getting all records normally
                try:
                    records = worksheet.get_all_records()
                    if records:
                        df = pd.DataFrame(records)
                        data[worksheet.title] = df
                        st.success(f"✅ Loaded '{worksheet.title}': {len(df)} rows")
                except Exception as header_error:
                    # If header issue, try alternative method
                    if "header row" in str(header_error).lower() and "not unique" in str(header_error).lower():
                        st.warning(f"⚠️ '{worksheet.title}' has duplicate headers, using alternative loading method...")
                        
                        # Get all values and create DataFrame manually
                        all_values = worksheet.get_all_values()
                        if all_values and len(all_values) > 4:  # Need at least 5 rows (0-3 + header row 4)
                            # IMPORTANT: Headers are in row 4 (index 3), data starts from row 5 (index 4)
                            headers = all_values[3]  # Row 4 (0-indexed as 3)
                            data_rows = all_values[4:]  # Data starts from row 5 (0-indexed as 4)
                            
                            # Make headers unique and meaningful
                            unique_headers = []
                            header_counts = {}
                            
                            for i, header in enumerate(headers):
                                # Handle empty headers
                                if not header or header.strip() == "":
                                    header = f"Column_{i+1}"
                                
                                # Handle duplicate headers
                                original_header = header
                                counter = 0
                                while header in header_counts:
                                    counter += 1
                                    header = f"{original_header}_{counter}"
                                
                                header_counts[header] = True
                                unique_headers.append(header)
                            
                            # Create DataFrame with unique headers and correct data
                            df = pd.DataFrame(data_rows, columns=unique_headers)
                            data[worksheet.title] = df
                            st.success(f"✅ Loaded '{worksheet.title}': {len(df)} rows (fixed duplicate headers, headers from row 4)")
                        else:
                            st.warning(f"⚠️ '{worksheet.title}' appears to be empty")
                    else:
                        raise header_error
                        
            except Exception as e:
                st.warning(f"❌ Could not load worksheet '{worksheet.title}': {str(e)}")
                continue
        
        return data
        
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        st.info("Using test data instead. Please check your secrets configuration.")
        
        # Return test data as fallback
        return {
            'Sheet1': pd.DataFrame({
                'Theater': ['Theater A', 'Theater B', 'Theater C'],
                'Revenue': [1000, 1500, 2000],
                'Cost': [500, 750, 1000],
                'Event': ['Event 1', 'Event 2', 'Event 3']
            })
        }

def clean_currency_column(df, column_name):
    """Clean currency values like '$1,234.56' to float"""
    if column_name in df.columns:
        df[column_name] = df[column_name].astype(str).str.replace('$', '').str.replace(',', '')
        df[column_name] = pd.to_numeric(df[column_name], errors='coerce')
    return df

# Main navigation
st.title("🎫 TicketFusion Dashboard")
st.markdown("---")

# Load data
with st.spinner("Loading data from Google Sheets..."):
    sheets_data = load_google_sheets_data()

# Sidebar navigation
st.sidebar.title("Navigation")
app_choice = st.sidebar.selectbox(
    "Choose an application:",
    ["Home", "Google Sheets Analytics", "Account Availability Checker"]
)

if app_choice == "Home":
    st.header("Welcome to TicketFusion")
    st.write("Your integrated ticketing and analytics platform.")
    
    # Quick Summary
    if sheets_data:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 Total Sheets", len(sheets_data))
        with col2:
            total_rows = sum(len(df) for df in sheets_data.values())
            st.metric("📋 Total Records", f"{total_rows:,}")
        with col3:
            if 'Orders' in sheets_data:
                st.metric("🛒 Orders", len(sheets_data['Orders']))
            else:
                st.metric("🛒 Orders", "N/A")
        with col4:
            if 'Accounts' in sheets_data:
                st.metric("👥 Accounts", len(sheets_data['Accounts']))
            else:
                st.metric("👥 Accounts", "N/A")
        
        st.markdown("---")
    
    # Show basic data status
    st.subheader("📊 Data Status")
    if sheets_data:
        st.success(f"✅ Connected to Google Sheets - {len(sheets_data)} worksheets loaded")
        
        st.write("**Loaded sheets:**")
        for sheet_name, df in sheets_data.items():
            st.write(f"• **{sheet_name}**: {len(df)} rows, {len(df.columns)} columns")
    else:
        st.error("❌ No data loaded")

elif app_choice == "Google Sheets Analytics":
    st.header("📈 Analytics Dashboard")
    
    if not sheets_data:
        st.error("No data available for analytics")
        st.stop()
    
    # Sheet selection
    sheet_names = list(sheets_data.keys())
    selected_sheet = st.selectbox("Select data sheet:", sheet_names)
    
    if selected_sheet and selected_sheet in sheets_data:
        df = sheets_data[selected_sheet].copy()
        
        if df.empty:
            st.warning("Selected sheet is empty")
            st.stop()
        
        st.subheader(f"Data from: {selected_sheet}")
        
        # Show raw data
        with st.expander("📋 View Raw Data"):
            st.dataframe(df)
        
        # Show basic stats
        st.write(f"**Rows:** {len(df)}")
        st.write(f"**Columns:** {len(df.columns)}")
        st.write(f"**Column names:** {', '.join(df.columns)}")
        
        # Show sample data to help understand the structure
        if len(df) > 0:
            st.subheader("📋 Data Preview")
            
            # Show first few rows
            st.write("**First 3 rows:**")
            st.dataframe(df.head(3))
            
            # Show column info
            with st.expander("🔍 Column Details"):
                for i, col in enumerate(df.columns):
                    sample_values = df[col].dropna().head(3).tolist()
                    st.write(f"**Column {i+1}: {col}**")
                    if sample_values:
                        st.write(f"Sample values: {sample_values}")
                    else:
                        st.write("Sample values: [No data]")
                    st.write("---")

elif app_choice == "Account Availability Checker":
    st.header("🔍 Account Availability Analysis")
    
    if not sheets_data:
        st.error("No data available for availability analysis")
        st.stop()
    
    # Show available sheets
    st.subheader("📊 Available Data Sheets")
    sheet_names = list(sheets_data.keys())
    
    for sheet_name in sheet_names:
        df = sheets_data[sheet_name]
        st.write(f"• **{sheet_name}**: {len(df)} rows, {len(df.columns)} columns")
    
    # Basic availability info
    if 'ProfileAvailability' in sheets_data:
        df = sheets_data['ProfileAvailability']
        st.subheader("ProfileAvailability Summary")
        st.write(f"Total records: {len(df)}")
        st.dataframe(df.head())
    else:
        st.warning("ProfileAvailability sheet not found")