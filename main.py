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
                        # Only show success in debug mode
                        # st.success(f"✅ Loaded '{worksheet.title}': {len(df)} rows")
                except Exception as header_error:
                    # If header issue, try alternative method
                    if "header row" in str(header_error).lower() and "not unique" in str(header_error).lower():
                        try:
                            # st.warning(f"⚠️ '{worksheet.title}' has duplicate headers, using alternative loading method...")
                            
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
                                # Only show detailed success in debug mode  
                                # st.success(f"✅ Loaded '{worksheet.title}': {len(df)} rows (fixed duplicate headers, headers from row 4)")
                            else:
                                st.warning(f"⚠️ '{worksheet.title}' appears to be empty")
                        except Exception as fallback_error:
                            st.error(f"❌ Failed to load '{worksheet.title}': {fallback_error}")
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
    
    # Automatically use Orders data for analytics
    if 'Orders' in sheets_data:
        df = sheets_data['Orders'].copy()
    else:
        # Fallback to first available sheet
        df = list(sheets_data.values())[0].copy()
    
    if df.empty:
        st.warning("No order data available for analytics")
        st.stop()
    
    # Revenue Analysis - more flexible column detection
    revenue_cols = [col for col in df.columns if any(word in col.lower() for word in ['revenue', 'income', 'sales', 'amount', 'total', 'price', 'cost'])]
    cost_cols = [col for col in df.columns if any(word in col.lower() for word in ['cost', 'expense', 'fee', 'charge'])]
    
    # st.write(f"**Found potential financial columns**: {revenue_cols + cost_cols}")
    
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
    st.header("🎫 Account Availability Checker")
    
    if not sheets_data:
        st.error("No data available for availability checking")
        st.stop()
    
    # Automatically use ProfileAvailability data
    if 'ProfileAvailability' in sheets_data:
        df = sheets_data['ProfileAvailability'].copy()
        st.write(f"**Profile Availability Analysis** ({len(df)} records)")
        
        # Show data structure for understanding
        with st.expander("📋 View Data Structure"):
            st.write("**Sample data (first 3 rows):**")
            st.dataframe(df.head(3))
            st.write("**Column info:**")
            for i, col in enumerate(df.columns):
                st.write(f"{i}: {col}")
        
        # Availability Analysis Section
        st.subheader("🎯 Capacity Analysis")
        
        if len(df.columns) > 0:
            # The first column typically contains email addresses/profiles
            primary_col = df.columns[0]
            
            # Look for capacity-related columns (numeric data that might indicate available spots)
            capacity_cols = []
            for col in df.columns[1:]:  # Skip the first column (email)
                # Check if column contains numeric data that could represent capacity
                try:
                    # Convert to numeric and check if it has meaningful values
                    numeric_data = pd.to_numeric(df[col], errors='coerce')
                    if numeric_data.notna().any() and (numeric_data > 0).any():
                        capacity_cols.append(col)
                except:
                    pass
            
            st.write(f"**Found {len(capacity_cols)} potential capacity columns**")
            
            if capacity_cols:
                # Allow user to select which columns represent capacity/availability
                selected_capacity_cols = st.multiselect(
                    "Select columns that represent available capacity/spots:",
                    capacity_cols,
                    default=capacity_cols[:3] if len(capacity_cols) >= 3 else capacity_cols
                )
                
                if selected_capacity_cols:
                    # Set minimum capacity threshold
                    min_capacity = st.number_input("Minimum available capacity threshold:", min_value=0, value=1)
                    
                    if st.button("🔍 Find Available Profiles"):
                        st.subheader("📧 Profiles with Available Capacity")
                        
                        available_profiles = []
                        
                        for idx, row in df.iterrows():
                            profile_email = row[primary_col]
                            if pd.isna(profile_email) or str(profile_email).strip() == "":
                                continue
                                
                            # Check if this profile has capacity in any of the selected columns
                            has_capacity = False
                            capacity_details = {}
                            
                            for cap_col in selected_capacity_cols:
                                try:
                                    capacity_value = pd.to_numeric(row[cap_col], errors='coerce')
                                    if pd.notna(capacity_value) and capacity_value >= min_capacity:
                                        has_capacity = True
                                        capacity_details[cap_col] = capacity_value
                                except:
                                    pass
                            
                            if has_capacity:
                                available_profiles.append({
                                    'Email': profile_email,
                                    'Total_Capacity': sum(capacity_details.values()),
                                    'Details': capacity_details
                                })
                        
                        if available_profiles:
                            st.success(f"✅ Found {len(available_profiles)} profiles with available capacity!")
                            
                            # Display results
                            results_df = pd.DataFrame([
                                {
                                    'Email': p['Email'],
                                    'Total Available Capacity': p['Total_Capacity'],
                                    'Capacity Breakdown': ', '.join([f"{k}: {v}" for k, v in p['Details'].items()])
                                }
                                for p in available_profiles
                            ])
                            
                            st.dataframe(results_df)
                            
                            # Summary metrics
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Available Profiles", len(available_profiles))
                            with col2:
                                total_capacity = sum(p['Total_Capacity'] for p in available_profiles)
                                st.metric("Total Available Capacity", int(total_capacity))
                            with col3:
                                avg_capacity = total_capacity / len(available_profiles) if available_profiles else 0
                                st.metric("Average Capacity per Profile", f"{avg_capacity:.1f}")
                            
                            # Export option
                            csv = results_df.to_csv(index=False)
                            st.download_button(
                                label="📥 Download Results as CSV",
                                data=csv,
                                file_name="available_profiles.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning(f"❌ No profiles found with capacity >= {min_capacity}")
                            st.info("Try adjusting the minimum capacity threshold or check your column selections.")
                else:
                    st.warning("Please select at least one capacity column to analyze.")
            else:
                st.error("No numeric columns found that could represent capacity data.")
                st.info("Make sure your ProfileAvailability data contains numeric columns representing available spots/capacity.")
        else:
            st.error("No columns available for analysis")
    else:
        st.error("ProfileAvailability sheet not found in the data")