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
                records = worksheet.get_all_records()
                if records:
                    df = pd.DataFrame(records)
                    data[worksheet.title] = df
            except Exception as e:
                st.warning(f"Could not load worksheet '{worksheet.title}': {str(e)}")
        
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
    
    # Show data status
    st.subheader("📊 Data Status")
    if sheets_data:
        st.success(f"✅ Connected to Google Sheets - {len(sheets_data)} worksheets loaded")
        for sheet_name, df in sheets_data.items():
            st.write(f"• **{sheet_name}**: {len(df)} rows, {len(df.columns)} columns")
    else:
        st.error("❌ No data loaded")
    
    # Show sample data
    if sheets_data:
        st.subheader("📋 Sample Data Preview")
        for sheet_name, df in list(sheets_data.items())[:2]:  # Show first 2 sheets
            with st.expander(f"View {sheet_name} data"):
                st.dataframe(df.head())

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
        
        # Revenue Analysis
        revenue_cols = [col for col in df.columns if 'revenue' in col.lower() or 'Revenue' in col]
        cost_cols = [col for col in df.columns if 'cost' in col.lower() or 'Cost' in col]
        
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
    
    # Sheet selection
    sheet_names = list(sheets_data.keys())
    selected_sheet = st.selectbox("Select data sheet:", sheet_names, key="avail_sheet")
    
    if selected_sheet and selected_sheet in sheets_data:
        df = sheets_data[selected_sheet].copy()
        
        if df.empty:
            st.warning("Selected sheet is empty")
            st.stop()
        
        # Theater selection
        theater_cols = [col for col in df.columns if 'theater' in col.lower() or 'Theater' in col]
        if theater_cols:
            theaters = df[theater_cols[0]].unique()
            selected_theater = st.selectbox("Select Theater:", theaters)
            
            if st.button("🔍 Analyze Availability"):
                theater_data = df[df[theater_cols[0]] == selected_theater]
                
                st.subheader(f"Analysis for {selected_theater}")
                
                # Show theater-specific data
                st.write(f"**Records found**: {len(theater_data)}")
                
                if not theater_data.empty:
                    st.dataframe(theater_data)
                    
                    # Email analysis (if email columns exist)
                    email_cols = [col for col in df.columns if 'email' in col.lower() or 'Email' in col]
                    if email_cols:
                        emails = theater_data[email_cols[0]].dropna().unique()
                        st.write(f"**Unique emails**: {len(emails)}")
                        
                        for email in emails[:10]:  # Show first 10
                            st.write(f"• {email}")
                else:
                    st.warning("No data found for selected theater")
        else:
            st.info("No theater column found in the data")
            st.write("Available columns:", list(df.columns))

# Footer
st.markdown("---")
st.markdown("*TicketFusion Dashboard - Powered by Google Sheets*")