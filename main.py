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
                        if all_values and len(all_values) > 1:
                            # Use first row as headers, but make them unique
                            headers = all_values[0]
                            unique_headers = []
                            header_counts = {}
                            
                            for header in headers:
                                if header in header_counts:
                                    header_counts[header] += 1
                                    unique_header = f"{header}_{header_counts[header]}"
                                else:
                                    header_counts[header] = 0
                                    unique_header = header
                                unique_headers.append(unique_header)
                            
                            # Create DataFrame with unique headers
                            df = pd.DataFrame(all_values[1:], columns=unique_headers)
                            data[worksheet.title] = df
                            st.success(f"✅ Loaded '{worksheet.title}': {len(df)} rows (fixed duplicate headers)")
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
    
    # Show data status
    try:
        st.subheader("📊 Data Status")
        if sheets_data:
            st.success(f"✅ Connected to Google Sheets - {len(sheets_data)} worksheets loaded")
            
            # Simple list view first
            st.write("**Loaded sheets:**")
            for sheet_name, df in sheets_data.items():
                st.write(f"• **{sheet_name}**: {len(df)} rows, {len(df.columns)} columns")
            
            # Advanced details in collapsible section
            with st.expander("� View Detailed Sheet Information"):
                for sheet_name, df in sheets_data.items():
                    try:
                        st.write(f"**{sheet_name}**")
                        
                        if not df.empty and len(df.columns) > 0:
                            # Show columns safely
                            col_names = [str(col) for col in df.columns]
                            if len(col_names) > 10:
                                st.write(f"Columns: {', '.join(col_names[:10])}... (+{len(col_names)-10} more)")
                            else:
                                st.write(f"Columns: {', '.join(col_names)}")
                            
                            # Show one sample row
                            if len(df) > 0:
                                st.write("Sample row:")
                                try:
                                    sample_row = df.iloc[0].to_dict()
                                    # Limit display to first 5 columns to avoid overflow
                                    sample_display = {k: str(v)[:50] + "..." if len(str(v)) > 50 else str(v) 
                                                    for k, v in list(sample_row.items())[:5]}
                                    st.json(sample_display)
                                except Exception:
                                    st.write("*Sample data not displayable*")
                        else:
                            st.write("*Empty sheet*")
                        
                        st.write("---")
                        
                    except Exception as e:
                        st.write(f"Error with {sheet_name}: {str(e)}")
                        st.write("---")
        else:
            st.error("❌ No data loaded")
    
    except Exception as e:
        st.error(f"Error in data status section: {str(e)}")
        st.write("Sheets loaded:", list(sheets_data.keys()) if sheets_data else "None")
    
    # Debug checkpoint
    st.write("🔧 Debug: Reached end of data status section")
    
    # Show sample data
    try:
        if sheets_data:
            st.subheader("📋 Quick Start")
            st.write("Your data is loaded and ready! Use the navigation sidebar to:")
            st.write("• **Google Sheets Analytics** - View charts and financial analysis")
            st.write("• **Account Availability Checker** - Analyze profiles and availability")
            
            # Show key sheets available
            key_sheets = ['Orders', 'Accounts', 'ProfileAvailability', 'Venues']
            available_key_sheets = [sheet for sheet in key_sheets if sheet in sheets_data]
            
            if available_key_sheets:
                st.write(f"**Key data sheets available**: {', '.join(available_key_sheets)}")
            
            st.success("✅ All systems ready - select a tab from the sidebar to get started!")
    
    except Exception as e:
        st.error(f"Error in sample data section: {str(e)}")
    
    # Final debug checkpoint
    st.write("🔧 Debug: Completed Home page render")

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
        
        # Revenue Analysis - more flexible column detection
        revenue_cols = [col for col in df.columns if any(word in col.lower() for word in ['revenue', 'income', 'sales', 'amount', 'total', 'price', 'cost'])]
        cost_cols = [col for col in df.columns if any(word in col.lower() for word in ['cost', 'expense', 'fee', 'charge'])]
        
        st.write(f"**Found potential financial columns**: {revenue_cols + cost_cols}")
        
        if revenue_cols or cost_cols:
            st.subheader("💰 Financial Analysis")
            
            col1, col2 = st.columns(2)
            
            # Revenue chart
            if revenue_cols:
                with col1:
                    st.write("**Revenue Analysis**")
                    revenue_col = revenue_cols[0]
                    
                    # Clean currency data
                    df = clean_currency_column(df, revenue_col)
                    
                    if df[revenue_col].notna().any():
                        if 'Theater' in df.columns:
                            fig_revenue = px.bar(df, x='Theater', y=revenue_col, 
                                              title=f'Revenue by Theater')
                        else:
                            fig_revenue = px.bar(df, y=revenue_col, 
                                              title=f'Revenue Distribution')
                        st.plotly_chart(fig_revenue, use_container_width=True)
                        
                        # Revenue stats
                        total_revenue = df[revenue_col].sum()
                        avg_revenue = df[revenue_col].mean()
                        st.metric("Total Revenue", f"${total_revenue:,.2f}")
                        st.metric("Average Revenue", f"${avg_revenue:,.2f}")
            
            # Cost chart
            if cost_cols:
                with col2:
                    st.write("**Cost Analysis**")
                    cost_col = cost_cols[0]
                    
                    # Clean currency data
                    df = clean_currency_column(df, cost_col)
                    
                    if df[cost_col].notna().any():
                        if 'Theater' in df.columns:
                            fig_cost = px.bar(df, x='Theater', y=cost_col, 
                                            title=f'Cost by Theater', color_discrete_sequence=['red'])
                        else:
                            fig_cost = px.bar(df, y=cost_col, 
                                            title=f'Cost Distribution', color_discrete_sequence=['red'])
                        st.plotly_chart(fig_cost, use_container_width=True)
                        
                        # Cost stats
                        total_cost = df[cost_col].sum()
                        avg_cost = df[cost_col].mean()
                        st.metric("Total Cost", f"${total_cost:,.2f}")
                        st.metric("Average Cost", f"${avg_cost:,.2f}")
            
            # Profit analysis
            if revenue_cols and cost_cols:
                st.subheader("📊 Profit Analysis")
                revenue_col = revenue_cols[0]
                cost_col = cost_cols[0]
                
                df['Profit'] = df[revenue_col] - df[cost_col]
                
                if 'Theater' in df.columns:
                    fig_profit = px.bar(df, x='Theater', y='Profit', 
                                      title='Profit by Theater',
                                      color='Profit',
                                      color_continuous_scale='RdYlGn')
                    st.plotly_chart(fig_profit, use_container_width=True)
                
                total_profit = df['Profit'].sum()
                avg_profit = df['Profit'].mean()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Profit", f"${total_profit:,.2f}")
                with col2:
                    st.metric("Average Profit", f"${avg_profit:,.2f}")
        
        else:
            st.info("No revenue or cost columns found in the selected sheet.")
            st.write("Available columns:", list(df.columns))

elif app_choice == "Account Availability Checker":
    st.header("🔍 Account Availability Analysis")
    
    if not sheets_data:
        st.error("No data available for availability analysis")
        st.stop()
    
    # Show available sheets for selection
    st.subheader("📊 Available Data Sheets")
    sheet_names = list(sheets_data.keys())
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Orders & Financial Data:**")
        financial_sheets = [name for name in sheet_names if any(word in name.lower() for word in ['order', 'payment', 'stefan'])]
        for sheet in financial_sheets:
            st.write(f"• {sheet} ({len(sheets_data[sheet])} rows)")
    
    with col2:
        st.write("**Profile & Availability Data:**")
        profile_sheets = [name for name in sheet_names if any(word in name.lower() for word in ['profile', 'account', 'availability'])]
        for sheet in profile_sheets:
            st.write(f"• {sheet} ({len(sheets_data[sheet])} rows)")
    
    # Main analysis section
    st.subheader("🎯 Analysis Options")
    
    analysis_type = st.selectbox(
        "Choose analysis type:",
        ["Profile Availability Analysis", "Account Capacity Analysis", "Venue Analysis"]
    )
    
    if analysis_type == "Profile Availability Analysis":
        if 'ProfileAvailability' in sheets_data:
            df = sheets_data['ProfileAvailability'].copy()
            st.write(f"**Analyzing ProfileAvailability data** ({len(df)} records)")
            
            # Show column structure
            with st.expander("📋 Data Structure"):
                st.write("**Columns available:**", list(df.columns))
                st.dataframe(df.head())
            
            # Look for venue/theater columns
            venue_cols = [col for col in df.columns if any(word in col.lower() for word in ['venue', 'theater', 'theatre', 'location'])]
            if venue_cols:
                venue_col = venue_cols[0]
                venues = df[venue_col].dropna().unique()
                selected_venue = st.selectbox("Select Venue/Theater:", venues)
                
                if st.button("🔍 Analyze Availability"):
                    venue_data = df[df[venue_col] == selected_venue]
                    
                    st.subheader(f"Results for {selected_venue}")
                    st.write(f"**Records found**: {len(venue_data)}")
                    
                    if not venue_data.empty:
                        st.dataframe(venue_data)
                        
                        # Look for email columns
                        email_cols = [col for col in venue_data.columns if 'email' in col.lower()]
                        if email_cols:
                            emails = venue_data[email_cols[0]].dropna().unique()
                            st.write(f"**Available profiles**: {len(emails)}")
                            for email in emails:
                                st.write(f"• {email}")
            else:
                st.info("No venue/theater column found. Available columns: " + ", ".join(df.columns))
        else:
            st.warning("ProfileAvailability sheet not found")
    
    elif analysis_type == "Account Capacity Analysis":
        if 'Accounts' in sheets_data:
            df = sheets_data['Accounts'].copy()
            st.write(f"**Analyzing Accounts data** ({len(df)} records)")
            
            with st.expander("📋 Data Structure"):
                st.write("**Columns available:**", list(df.columns))
                st.dataframe(df.head())
            
            # Theater/venue analysis
            theater_cols = [col for col in df.columns if any(word in col.lower() for word in ['theater', 'venue', 'location'])]
            if theater_cols:
                theater_col = theater_cols[0]
                theaters = df[theater_col].dropna().unique()
                selected_theater = st.selectbox("Select Theater:", theaters)
                
                if st.button("🔍 Analyze Capacity"):
                    theater_data = df[df[theater_col] == selected_theater]
                    
                    st.subheader(f"Capacity Analysis for {selected_theater}")
                    st.write(f"**Accounts at this theater**: {len(theater_data)}")
                    
                    if not theater_data.empty:
                        st.dataframe(theater_data)
            else:
                st.info("No theater column found. Available columns: " + ", ".join(df.columns))
        else:
            st.warning("Accounts sheet not found")
    
    elif analysis_type == "Venue Analysis":
        if 'Venues' in sheets_data:
            df = sheets_data['Venues'].copy()
            st.write(f"**Analyzing Venues data** ({len(df)} records)")
            
            with st.expander("📋 Data Structure"):
                st.write("**Columns available:**", list(df.columns))
                st.dataframe(df.head())
            
            # Show all venues
            st.subheader("📍 All Venues")
            st.dataframe(df)
        else:
            st.warning("Venues sheet not found")

# Footer
st.markdown("---")
st.markdown("*TicketFusion Dashboard - Powered by Google Sheets*")