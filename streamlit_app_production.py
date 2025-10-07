import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import toml
import io
from io import BytesIO
import openpyxl
from tempfile import NamedTemporaryFile

# Configure the page
st.set_page_config(
    page_title="TicketFusion Dashboard - Production", 
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_header_row_for_sheet(sheet_name):
    """
    Determine which row contains headers based on sheet name.
    Only 'Ordres' sheet uses Row 4, others use Row 1.
    """
    ordres_sheets = ['Ordres', 'ordres', 'ORDRES', 'Orders', 'orders', 'ORDERS']
    return 4 if sheet_name in ordres_sheets else 1

def should_skip_error_checking(sheet_name):
    """
    Determine if error checking should be skipped for this sheet.
    Stefan Payments and Limits tabs are not critical and can be skipped.
    """
    skip_sheets = ['Stefan Payments', 'stefan payments', 'STEFAN PAYMENTS', 
                   'Limits', 'limits', 'LIMITS']
    return sheet_name in skip_sheets

def check_email_availability(email, orders, today, event=None, theater=None, event_date=None, cnt_new=1, sold_date_new=None):
    """
    Simplified availability checker without database dependencies
    """
    # Check if orders DataFrame is valid and has required columns
    if orders is None or orders.empty:
        return True, ["No order data available"]
    
    # Check for email column - try different possible names
    email_col = None
    for col in ["email", "Email", "EMAIL", "user_email", "customer_email"]:
        if col in orders.columns:
            email_col = col
            break
    
    if email_col is None:
        return True, ["Email column not found in order data"]
    
    try:
        # Filter orders for this email
        user_orders = orders[orders[email_col].astype(str).str.lower().str.strip() == email.lower().strip()]
    except Exception:
        return True, ["Error filtering orders by email"]
    
    if user_orders.empty:
        return True, []
    
    # Apply the three availability rules
    reasons = []
    is_available = True
    
    try:
        # Rule 1: No more than 6 tickets in the last 12 months
        if 'sold_date' in user_orders.columns and 'cnt' in user_orders.columns:
            twelve_months_ago = today - timedelta(days=365)
            recent_orders = user_orders[
                pd.to_datetime(user_orders['sold_date'], errors='coerce') >= twelve_months_ago
            ]
            total_tickets_12m = recent_orders['cnt'].sum()
            
            if total_tickets_12m + cnt_new > 6:
                is_available = False
                reasons.append(f"Would exceed 6 tickets in 12 months (current: {total_tickets_12m}, requesting: {cnt_new})")
        
        # Rule 2: No more than 4 tickets for the same event
        if event and 'event' in user_orders.columns and 'cnt' in user_orders.columns:
            event_orders = user_orders[
                user_orders['event'].astype(str).str.contains(event, case=False, na=False)
            ]
            total_tickets_event = event_orders['cnt'].sum()
            
            if total_tickets_event + cnt_new > 4:
                is_available = False
                reasons.append(f"Would exceed 4 tickets for event '{event}' (current: {total_tickets_event}, requesting: {cnt_new})")
        
        # Rule 3: No purchases within 30 days of event date
        if event_date and sold_date_new and 'sold_date' in user_orders.columns:
            days_before_event = (event_date - sold_date_new).days
            
            if days_before_event < 30:
                # Check if user has existing orders for events close to this date
                user_orders['event_date'] = pd.to_datetime(user_orders.get('event_date', []), errors='coerce')
                close_orders = user_orders[
                    abs((user_orders['event_date'] - event_date).dt.days) <= 30
                ]
                
                if not close_orders.empty:
                    is_available = False
                    reasons.append(f"Cannot purchase within 30 days of event (purchase date: {sold_date_new.date()}, event date: {event_date.date()})")
    
    except Exception as e:
        # If there's any error in rule checking, default to available
        reasons.append(f"Rule checking error: {str(e)}")
        
    return is_available, reasons

def upload_xlsx_to_template_sheet(xlsx_file, template_sheet_id):
    """
    Upload XLSX data to an existing Google Sheet (template sheet) - avoids quota issues
    """
    try:
        # Get credentials for Google Sheets API
        try:
            credentials_dict = dict(st.secrets["google_service_account"])
        except Exception:
            with open("STREAMLIT_SECRETS_READY.toml", "r") as f:
                secrets = toml.load(f)
                credentials_dict = dict(secrets["google_service_account"])
        
        # Define the required scopes
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Create credentials
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        gc = gspread.authorize(credentials)
        
        # Read XLSX file directly from memory
        from io import BytesIO
        xlsx_bytes = BytesIO(xlsx_file.getvalue())
        
        # Load the first sheet from XLSX (primary data)
        xl_file = pd.ExcelFile(xlsx_bytes)
        first_sheet_name = xl_file.sheet_names[0]
        
        # Use flexible header detection based on sheet name
        header_row = get_header_row_for_sheet(first_sheet_name)
        skiprows = header_row - 1 if header_row > 1 else 0
        df = pd.read_excel(xlsx_bytes, sheet_name=first_sheet_name, skiprows=skiprows)
        
        # Open the existing template sheet
        spreadsheet = gc.open_by_key(template_sheet_id)
        worksheet = spreadsheet.get_worksheet(0)  # Use the first worksheet
        
        # Clear existing data
        worksheet.clear()
        
        # Convert DataFrame to list format for upload
        # Handle NaN values and data types for JSON serialization
        df_clean = df.copy()
        
        # Replace NaN values
        df_clean = df_clean.fillna('')
        
        # Convert datetime columns to strings
        for col in df_clean.columns:
            if df_clean[col].dtype == 'datetime64[ns]':
                df_clean[col] = df_clean[col].dt.strftime('%Y-%m-%d %H:%M:%S')
            elif 'datetime' in str(df_clean[col].dtype):
                df_clean[col] = df_clean[col].astype(str)
            elif 'time' in str(df_clean[col].dtype):
                df_clean[col] = df_clean[col].astype(str)
        
        # Upload data to the template sheet
        values = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
        worksheet.update(values)
        
        return True
        
    except Exception as e:
        st.error(f"Failed to upload to template sheet: {e}")
        return False

def create_google_sheet_from_xlsx(xlsx_file, sheet_name_prefix="TicketFusion_Production"):
    """
    Create a new Google Sheet from XLSX file data
    """
    try:
        # Get credentials for Google Sheets API
        try:
            credentials_dict = dict(st.secrets["google_service_account"])
        except Exception:
            with open("STREAMLIT_SECRETS_READY.toml", "r") as f:
                secrets = toml.load(f)
                credentials_dict = dict(secrets["google_service_account"])
        
        # Define the required scopes
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Create credentials
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        gc = gspread.authorize(credentials)
        
        # Read XLSX file directly from memory
        xlsx_data = {}
        
        # Create a BytesIO object from the uploaded file
        xlsx_bytes = BytesIO(xlsx_file.getvalue())
        
        # Load all sheets from XLSX
        xl_file = pd.ExcelFile(xlsx_bytes)
        for sheet_name in xl_file.sheet_names:
            # Skip error-prone sheets like Stefan Payments
            if should_skip_error_checking(sheet_name):
                continue
                
            # Use flexible header detection based on sheet name
            header_row = get_header_row_for_sheet(sheet_name)
            skiprows = header_row - 1 if header_row > 1 else 0
            df = pd.read_excel(xlsx_bytes, sheet_name=sheet_name, skiprows=skiprows)
            xlsx_data[sheet_name] = df
        
        # Create a new Google Sheet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_sheet_name = f"{sheet_name_prefix}_{timestamp}"
        
        # Create the spreadsheet
        spreadsheet = gc.create(new_sheet_name)
        
        # Share with the service account (make it accessible)
        spreadsheet.share(credentials_dict['client_email'], perm_type='user', role='writer')
        
        # Get the default sheet and rename it to the first XLSX sheet name
        first_sheet_name = list(xlsx_data.keys())[0]
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.update_title(first_sheet_name)
        
        # Upload the first sheet data
        df = xlsx_data[first_sheet_name]
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        
        # Add additional sheets if they exist
        for sheet_name, df in list(xlsx_data.items())[1:]:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(df)+1, cols=len(df.columns))
            worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        
        return spreadsheet.id, spreadsheet.url, new_sheet_name
        
    except Exception as e:
        st.error(f"Failed to create Google Sheet: {e}")
        return None, None, None

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_google_sheets_data(doc_id=None):
    """Load data from Google Sheets with proper error handling"""
    try:
        # Try to get credentials from Streamlit secrets, fallback to direct file read
        if doc_id is None:
            try:
                credentials_dict = dict(st.secrets["google_service_account"])
                doc_id = st.secrets["GOOGLE_SHEETS_DOC_ID"]
            except Exception:
                # Fallback: read directly from the ready file
                with open("STREAMLIT_SECRETS_READY.toml", "r") as f:
                    secrets = toml.load(f)
                    credentials_dict = dict(secrets["google_service_account"])
                    doc_id = secrets["GOOGLE_SHEETS_DOC_ID"]
        else:
            # Use provided doc_id with credentials
            try:
                credentials_dict = dict(st.secrets["google_service_account"])
            except Exception:
                with open("STREAMLIT_SECRETS_READY.toml", "r") as f:
                    secrets = toml.load(f)
                    credentials_dict = dict(secrets["google_service_account"])
        
        # Define the required scopes for Google Sheets
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Create credentials with proper scopes
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        
        # Connect to Google Sheets
        gc = gspread.authorize(credentials)
        
        # Open the sheet using the document ID
        sheet = gc.open_by_key(doc_id)
        
        # Get all worksheets
        worksheets = sheet.worksheets()
        worksheet_names = [ws.title for ws in worksheets]
        
        # Load data from each worksheet
        data = {}
        for worksheet in worksheets:
            # Skip error-prone sheets
            if should_skip_error_checking(worksheet.title):
                continue
                
            try:
                # Determine appropriate header row for this sheet
                header_row = get_header_row_for_sheet(worksheet.title)
                
                # First try getting all records normally (for Row 1 headers)
                if header_row == 1:
                    try:
                        records = worksheet.get_all_records()
                        if records:
                            df = pd.DataFrame(records)
                            # Check if we got proper headers or just Unnamed columns
                            if not any(col.startswith('Unnamed:') for col in df.columns):
                                data[worksheet.title] = df
                                continue
                    except Exception:
                        pass
                
                # For Row 4 headers or if Row 1 failed, use manual method
                all_values = worksheet.get_all_values()
                
                if all_values and len(all_values) >= header_row:
                    headers = all_values[header_row - 1]  # Convert to 0-based index
                    data_rows = all_values[header_row:]  # Data starts after header row
                    
                    # Clean up headers - remove empty ones and make unique
                    clean_headers = []
                    for i, header in enumerate(headers):
                        if header and header.strip():
                            clean_headers.append(header.strip())
                        else:
                            clean_headers.append(f"Column_{i+1}")
                    
                    # Filter out empty data rows
                    filtered_data_rows = [row for row in data_rows if any(cell.strip() for cell in row if cell)]
                    
                    if filtered_data_rows:
                        # Create DataFrame with proper length matching
                        max_cols = len(clean_headers)
                        aligned_data = []
                        for row in filtered_data_rows:
                            # Pad or trim row to match header length
                            if len(row) < max_cols:
                                row.extend([''] * (max_cols - len(row)))
                            elif len(row) > max_cols:
                                row = row[:max_cols]
                            aligned_data.append(row)
                        
                        df = pd.DataFrame(aligned_data, columns=clean_headers)
                        data[worksheet.title] = df
                        
            except Exception:
                # Silently skip problematic sheets instead of showing errors
                data[worksheet.title] = pd.DataFrame()
        
        return data
        
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

def clean_currency_column(df, column_name):
    """Clean currency values like '$1,234.56' to float"""
    if column_name in df.columns:
        df[column_name] = df[column_name].astype(str).str.replace('$', '').str.replace(',', '')
        df[column_name] = pd.to_numeric(df[column_name], errors='coerce')
    return df

def main():
    st.title("🎫 TicketFusion Dashboard - Production Data")
    st.markdown("---")
    
    # Data Source Selection
    st.sidebar.header("📊 Data Source")
    data_source = st.sidebar.radio(
        "Choose data source:",
        ["Test Data (Google Sheets)", "Production Data (XLSX Upload)"],
        index=1  # Default to Production Data
    )
    
    sheets_data = None
    

    if data_source == "Test Data (Google Sheets)":
        # Load from existing test Google Sheets
        with st.spinner("Loading test data from Google Sheets..."):
            sheets_data = load_google_sheets_data()
    else:  # Production Data (XLSX Upload)
        st.sidebar.subheader("📤 Production Data Options")
        template_sheet_id = st.sidebar.text_input(
            "Template Google Sheet ID:",
            value="1HcNCioqz8azE51WMF-XAux6byVKfuU_vgqUCbTLVt34",
            help="Pre-configured template sheet ID for XLSX uploads"
        )
        uploaded_file = st.sidebar.file_uploader(
            "Choose XLSX file",
            type=['xlsx'],
            help="Upload your production data XLSX file to replace template sheet data"
        )
        if uploaded_file is not None:
            if st.sidebar.button("📋 Upload to Template Sheet", type="primary"):
                with st.spinner("Uploading data to template sheet..."):
                    success = upload_xlsx_to_template_sheet(uploaded_file, template_sheet_id)
                    if success:
                        st.success("✅ Data uploaded successfully!")
                        st.session_state['production_sheet_id'] = template_sheet_id
                        # Auto-load the template sheet
                        with st.spinner("Loading data..."):
                            sheets_data = load_google_sheets_data(template_sheet_id)
                            if sheets_data:
                                st.session_state['sheets_data'] = sheets_data
                    else:
                        st.error("❌ Upload failed. Please try again.")
        # If we have a production sheet ID stored, offer to load it
        if 'production_sheet_id' in st.session_state:
            st.sidebar.markdown("---")
            if st.sidebar.button("📊 Load Production Data"):
                with st.spinner("Loading production data..."):
                    sheets_data = load_google_sheets_data(st.session_state['production_sheet_id'])
            # Option to view the sheet
            if st.sidebar.button("👁️ View Sheet in Browser"):
                if 'production_sheet_url' in st.session_state:
                    st.sidebar.markdown(f"[🔗 Open Google Sheet]({st.session_state['production_sheet_url']})")
                else:
                    # Construct URL from sheet ID if URL not available
                    sheet_id = st.session_state.get('production_sheet_id', '')
                    if sheet_id:
                        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
                        st.sidebar.markdown(f"[🔗 Open Google Sheet]({sheet_url})")
                    else:
                        st.sidebar.error("No sheet available to view")

    # Sidebar navigation
    st.sidebar.title("Navigation")
    app_choice = st.sidebar.selectbox(
        "Choose an application:",
        ["Home", "Analytics", "Account Availability Checker"]
    )
    
    if app_choice == "Home":
        st.header("Welcome to TicketFusion - Production Version")
        st.write("Your integrated ticketing and analytics platform with production data support.")
        
        # Data source info
        if data_source == "Production Data (XLSX Upload)":
            st.info("🏭 **Production Mode**: Upload XLSX files to create Google Sheet copies for analysis")
            
            if 'production_sheet_id' in st.session_state:
                st.success(f"✅ Production sheet loaded: {st.session_state['production_sheet_id']}")
            else:
                st.warning("⚠️ No production data loaded. Upload an XLSX file to get started.")
        else:
            st.info("🧪 **Test Mode**: Using test Google Sheets data")
        
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

    elif app_choice == "Analytics":
        st.header("📈 Analytics Dashboard")
        
        # Auto-load data if we have a production sheet ID but no sheets_data
        if not sheets_data and 'production_sheet_id' in st.session_state:
            with st.spinner("Loading production data for analytics..."):
                sheets_data = load_google_sheets_data(st.session_state['production_sheet_id'])
                if sheets_data:
                    st.session_state['sheets_data'] = sheets_data
        
        if not sheets_data:
            st.error("No data available for analytics")
            st.write("Please upload XLSX data using the sidebar options.")
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
                        # Revenue stats
                        total_revenue = df[revenue_col].sum()
                        avg_revenue = df[revenue_col].mean()
                        st.metric("Total Revenue", f"${total_revenue:,.2f}")
                        st.metric("Average Revenue", f"${avg_revenue:,.2f}")
            
            # Cost metrics
            if cost_cols:
                with col2:
                    st.write("**Cost Analysis**")
                    cost_col = cost_cols[0]
                    
                    # Clean currency data
                    df = clean_currency_column(df, cost_col)
                    
                    if df[cost_col].notna().any():
                        # Cost stats
                        total_cost = df[cost_col].sum()
                        avg_cost = df[cost_col].mean()
                        st.metric("Total Cost", f"${total_cost:,.2f}")
                        st.metric("Average Cost", f"${avg_cost:,.2f}")
            
            # Time-based charts section
            st.subheader("📅 Trends Over Time")
            
            # Check for date columns for time-based analysis
            date_cols = [col for col in df.columns if any(word in col.lower() for word in ['date', 'time', 'sold', 'event'])]
            
            if date_cols and (revenue_cols or cost_cols):
                # Use the first available date column
                date_col = date_cols[0]
                
                # Convert to datetime
                try:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                    df_time = df.dropna(subset=[date_col]).copy()
                    
                    if not df_time.empty:
                        # Group by date and sum values
                        df_time['date_only'] = df_time[date_col].dt.date
                        
                        if revenue_cols and cost_cols:
                            daily_data = df_time.groupby('date_only').agg({
                                revenue_cols[0]: 'sum',
                                cost_cols[0]: 'sum'
                            }).reset_index()
                            daily_data['profit'] = daily_data[revenue_cols[0]] - daily_data[cost_cols[0]]
                        elif revenue_cols:
                            daily_data = df_time.groupby('date_only').agg({revenue_cols[0]: 'sum'}).reset_index()
                        
                        chart_cols = st.columns(2)
                        
                        # Revenue over time
                        if revenue_cols:
                            with chart_cols[0]:
                                fig_revenue_time = px.line(daily_data, x='date_only', y=revenue_cols[0],
                                                         title='Revenue Over Time',
                                                         labels={'date_only': 'Date', revenue_cols[0]: 'Revenue ($)'})
                                fig_revenue_time.update_traces(line_color='#1f77b4')
                                st.plotly_chart(fig_revenue_time, use_container_width=True)
                        
                        # Profit over time (if both revenue and cost exist)
                        if revenue_cols and cost_cols:
                            with chart_cols[1]:
                                fig_profit_time = px.line(daily_data, x='date_only', y='profit',
                                                        title='Profit Over Time',
                                                        labels={'date_only': 'Date', 'profit': 'Profit ($)'})
                                fig_profit_time.update_traces(line_color='#2ca02c')
                                st.plotly_chart(fig_profit_time, use_container_width=True)
                                
                except Exception as e:
                    st.warning(f"Could not create time-based charts: {e}")
        else:
            st.info("No revenue or cost columns found in the selected sheet.")
            st.write("Available columns:", list(df.columns))

    elif app_choice == "Account Availability Checker":
        st.header("🎫 Account Availability Checker")
        st.write("Check ticket availability for specific events using the three availability rules")
        
        # Auto-load data if we have a production sheet ID but no sheets_data
        if not sheets_data and 'production_sheet_id' in st.session_state:
            with st.spinner("Loading production data for availability checker..."):
                sheets_data = load_google_sheets_data(st.session_state['production_sheet_id'])
                if sheets_data:
                    st.session_state['sheets_data'] = sheets_data
        
        # Load theater-to-platform mapping from CSV file FIRST
        THEATER_PLATFORM_MAPPING = {}
        try:
            mapping_df = pd.read_csv('TheaterMapping_v2.csv')
            # Create dictionary: Theater -> Venue Platform
            for _, row in mapping_df.iterrows():
                theater_name = row['Theater'].strip()
                platform_name = row['Venue Platform'].strip()
                THEATER_PLATFORM_MAPPING[theater_name] = platform_name
        except Exception:
            # Fallback to manual mappings if CSV fails
            THEATER_PLATFORM_MAPPING = {
                "Academy of Music at Kimmel": "Ensemble",
                "Buell Theatre": "Denver Center",
                "Steinmetz Hall": "Dr Phillips", 
                "Walt Disney Theater": "Dr Phillips",
                "Des Moines Civic Center": "Des Moines Civic Center",
            }
        
        # === Sidebar Controls ===
        st.sidebar.header("Prospective Purchase Details")
        
        # Get orders data for existing events/theaters
        orders_df = None
        existing_theaters = []
        existing_events = []
        
        if sheets_data and 'Orders' in sheets_data:
            orders_df = sheets_data['Orders'].copy()
            
            # Column mapping for Orders data (Row 4 headers) - flexible matching
            column_mapping = {
                'sold_date': ['Sold Date', 'sold_date', 'SoldDate', 'Date Sold'],
                'event_date': ['Event Date', 'event_date', 'EventDate', 'Event_Date'], 
                'event': ['Event', 'event', 'Event Name', 'EventName'],
                'theater': ['Theater', 'theater', 'Theatre', 'Venue', 'venue'],
                'email': ['Email', 'email', 'Customer Email', 'User Email', 'customer_email'],
                'cnt': ['CNT', 'cnt', 'Count', 'Tickets', 'Quantity', 'Qty']
            }
            
            # Apply flexible column mapping
            for new_col, possible_names in column_mapping.items():
                for old_col in possible_names:
                    if old_col in orders_df.columns:
                        orders_df = orders_df.rename(columns={old_col: new_col})
                        break
            
            # Verify required columns exist
            required_cols = ['theater', 'event', 'email']
            missing_cols = [col for col in required_cols if col not in orders_df.columns]
            
            if missing_cols:
                st.sidebar.error(f"❌ Missing required columns: {missing_cols}")
                st.sidebar.write("Available columns:", list(orders_df.columns))
                st.stop()
            
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
                
        # Get unique venue platforms from the mapping
        available_platforms = []
        if THEATER_PLATFORM_MAPPING:
            available_platforms = sorted(set(THEATER_PLATFORM_MAPPING.values()))
        else:
            # Fallback to theater names if mapping failed
            if orders_df is not None and 'theater' in orders_df.columns:
                available_platforms = sorted(orders_df['theater'].dropna().astype(str).str.strip().unique().tolist())
        
        # Platform dropdown
        selected_platform = st.sidebar.selectbox("Venue Platform", options=[""] + available_platforms, index=0)
        
        # For backward compatibility, set theater variable to selected platform
        theater = selected_platform
        
        # Get events from orders data (use the already processed orders_df from above)
        existing_events = []
        if orders_df is not None and 'event' in orders_df.columns:
            # Filter out past events - only show future events
            current_events = orders_df.copy()
            if 'event_date' in current_events.columns:
                current_events['event_date'] = pd.to_datetime(current_events['event_date'], errors='coerce')
                today = pd.Timestamp.now().normalize()
                # Only include events that are today or in the future
                future_events = current_events[current_events['event_date'] >= today]
                existing_events = sorted(future_events['event'].dropna().astype(str).str.strip().unique().tolist())
            else:
                # If no event_date column, show all events (fallback)
                existing_events = sorted(orders_df['event'].dropna().astype(str).str.strip().unique().tolist())
        
        # Event dropdown - Platform-specific events
        if selected_platform and selected_platform.strip() and orders_df is not None:
            # Debug: Show platform and event data for troubleshooting
            st.sidebar.write(f"🔍 Selected Platform: '{selected_platform}'")
            
            # Show unique theaters/venues in orders data for this platform
            # Get all theaters that belong to this platform
            platform_theaters = [theater for theater, platform in THEATER_PLATFORM_MAPPING.items() if platform == selected_platform]
            
            # Get events for ANY theater that belongs to this platform
            all_platform_events = []
            for theater_name in platform_theaters:
                theater_events = orders_df[
                    orders_df['theater'].astype(str).str.strip() == theater_name
                ]['event'].dropna().astype(str).str.strip().unique().tolist()
                all_platform_events.extend(theater_events)
            
            # Remove duplicates and sort, then filter out past events
            unique_platform_events = sorted(list(set(all_platform_events)))
            
            # Filter out past events for platform-specific events too
            platform_events = []
            if 'event_date' in orders_df.columns:
                today = pd.Timestamp.now().normalize()
                for event in unique_platform_events:
                    event_rows = orders_df[orders_df['event'].astype(str).str.strip() == event]
                    if not event_rows.empty:
                        event_dates = pd.to_datetime(event_rows['event_date'], errors='coerce').dropna()
                        if not event_dates.empty and event_dates.iloc[0] >= today:
                            platform_events.append(event)
                    else:
                        # If no date data, include the event (fallback)
                        platform_events.append(event)
            else:
                platform_events = unique_platform_events
            
            if platform_events:
                event_choice = st.sidebar.selectbox(
                    f"Events in {selected_platform}", 
                    options=platform_events
                )
            else:
                event_choice = st.sidebar.selectbox("Choose event", options=["No events for this platform"], disabled=True)
        else:
            # No platform selected - show disabled event dropdown
            if not selected_platform or not selected_platform.strip():
                event_choice = st.sidebar.selectbox("Choose event", options=["Select platform first"], disabled=True)
            else:
                # Fallback case
                event_options = existing_events if existing_events else ["No events available"]
                event_choice = st.sidebar.selectbox("Choose event", options=event_options)
            
        # Set the event variable based on the selection
        if event_choice in ["Select platform first", "No events available", "No events for this platform"]:
            event = ""  # No valid event selected
        else:
            event = event_choice
        
        # REMOVED: event_date and sold_date inputs - use defaults
        # Fix 3: Remove ticket count input - use default of 1
        cnt = 1  # Fixed to 1, no input box needed
        
        # Get actual event and purchase dates from the selected event data
        event_date = None
        sold_date = datetime.now().date()  # Purchase date is today (when they're buying)
        
        if event and orders_df is not None and 'event' in orders_df.columns:
            # Find the selected event in the orders data to get its actual date
            event_rows = orders_df[orders_df['event'].astype(str).str.strip() == event]
            if not event_rows.empty and 'event_date' in orders_df.columns:
                # Get the most recent/common event date for this event
                event_dates = pd.to_datetime(event_rows['event_date'], errors='coerce').dropna()
                if not event_dates.empty:
                    event_date = event_dates.iloc[0].date()  # Use first valid date
        
        if event_date is None:
            event_date = datetime.now().date() + timedelta(days=30)  # Default to 30 days from now
        
        # Account data processing
        emails = []
        if sheets_data and 'Accounts' in sheets_data:
            df = sheets_data['Accounts'].copy()
            st.write(f"**Accounts Data** ({len(df)} records)")
            
            # For Accounts tab: Column A = Theater, Column C = Email (Row 1 headers)
            if len(df.columns) > 2:
                theater_col = df.columns[0]  # Column A (Theater)
                email_col = df.columns[2]    # Column C (Email)
                exclude_col = df.columns[12] if len(df.columns) > 12 else None  # Column M (Exclude)
                
                # Filter by selected platform if provided
                if selected_platform:
                    # Get all theaters that belong to this platform
                    platform_theaters = [theater for theater, platform in THEATER_PLATFORM_MAPPING.items() if platform == selected_platform]
                    
                    # Show what theaters actually exist in Accounts data
                    actual_theaters_in_accounts = sorted(df[theater_col].dropna().astype(str).str.strip().unique().tolist())
                    
                    # Check if the platform name itself exists in accounts (common pattern)
                    platform_variants = [selected_platform, selected_platform.replace("Tix", " Tix")]
                    matching_platform = None
                    for variant in platform_variants:
                        if variant in actual_theaters_in_accounts:
                            matching_platform = variant
                            break
                    
                    if matching_platform:
                        theater_data = df[df[theater_col].astype(str).str.strip() == matching_platform]
                    else:
                        # Fallback: Check for exact theater name matches
                        # Look up accounts for ANY theater in this platform
                        theater_data = df[df[theater_col].astype(str).str.strip().isin(platform_theaters)]
                    
                    if not theater_data.empty:
                        # Apply availability logic using Exclude column
                        if exclude_col and exclude_col in theater_data.columns:
                            # Filter out accounts that have exclusion dates
                            available_data = theater_data[theater_data[exclude_col].isna() | (theater_data[exclude_col] == '')]
                            excluded_data = theater_data[theater_data[exclude_col].notna() & (theater_data[exclude_col] != '')]
                            
                            emails = available_data[email_col].dropna().unique()
                            emails = [e for e in emails if str(e).strip() != "" and "@" in str(e) and "." in str(e)]
                            if len(excluded_data) > 0:
                                st.sidebar.info(f"ℹ️ {len(excluded_data)} accounts excluded")
                        else:
                            # No exclude column, use all emails
                            emails = theater_data[email_col].dropna().unique()
                            emails = [e for e in emails if str(e).strip() != "" and "@" in str(e) and "." in str(e)]
                        
                        # Show platform-specific insights
                        st.sidebar.info(f"📊 {len(theater_data)} total accounts")
                    else:
                        st.sidebar.error(f"❌ No accounts found for {selected_platform}")
                        emails = []
                else:
                    # Get all available emails (excluding those with exclusion dates)
                    if exclude_col and exclude_col in df.columns:
                        available_data = df[df[exclude_col].isna() | (df[exclude_col] == '')]
                        emails = available_data[email_col].dropna().unique()
                        emails = [e for e in emails if str(e).strip() != "" and "@" in str(e) and "." in str(e)]
                        st.sidebar.info(f"📊 {len(available_data)} total available accounts")
                    else:
                        emails = df[email_col].dropna().unique()
                        emails = [e for e in emails if str(e).strip() != "" and "@" in str(e) and "." in str(e)]
        
        # Run check button
        run_check = st.sidebar.button("🎯 Check Availability", type="primary")
        
        # Collapsible theater mappings (for reference) - placed after button
        with st.sidebar.expander("🗺️ View Theater → Platform Mappings", expanded=False):
            mapping_items = list(THEATER_PLATFORM_MAPPING.items())[:10]
            for theater_name, platform_name in mapping_items:
                st.write(f"• {theater_name} → {platform_name}")
            if len(THEATER_PLATFORM_MAPPING) > 10:
                st.write(f"... and {len(THEATER_PLATFORM_MAPPING) - 10} more")
        
        if run_check:
            if not emails:
                st.warning("No accounts found for the selected platform. Please select a platform or check your accounts data.")
                st.stop()
            
            today = datetime.now()
            sold_date = today.date()
            
            # Use venue platform as theater for checking
            venue_platform = selected_platform
            
            # Process availability checking
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, email in enumerate(emails):
                status_text.text(f"Checking {i+1}/{len(emails)}: {email}")
                progress_bar.progress((i + 1) / len(emails))
                
                is_available, reasons = check_email_availability(
                    email=email.lower().strip(),
                    orders=orders_df,
                    today=today,
                    event=event or None,
                    theater=venue_platform or None,  # Use venue platform instead of theater
                    event_date=pd.Timestamp(event_date) if event_date else None,
                    cnt_new=int(cnt),  # Convert to int
                    sold_date_new=pd.Timestamp(sold_date) if sold_date else None
                )
                
                results.append({
                    "email": email,
                    "available": is_available,
                    "reasons": "; ".join(reasons) if reasons else "Available",
                    "event": event or "N/A",
                    "platform": venue_platform or "N/A",
                    "event_date": event_date,
                    "tickets": cnt
                })
            
            status_text.text("✅ Check completed!")
            progress_bar.progress(1.0)
            
            # Results
            if results:
                results_df = pd.DataFrame(results)
                available_count = sum(1 for r in results if r["available"])
                unavailable_count = len(results) - available_count
                
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📧 Total Checked", len(results))
                with col2:
                    st.metric("✅ Available", available_count)
                with col3:
                    st.metric("❌ Unavailable", unavailable_count)
                
                # Show results tables
                if available_count > 0:
                    st.subheader("✅ Available Accounts")
                    available_df = results_df[results_df["available"] == True]
                    st.dataframe(available_df[["email", "event", "platform", "event_date", "tickets"]], use_container_width=True)
                
                if unavailable_count > 0:
                    st.subheader("❌ Unavailable Accounts")
                    unavailable_df = results_df[results_df["available"] == False]
                    st.dataframe(unavailable_df[["email", "reasons", "event", "platform"]], use_container_width=True)
                
                # Download button
                csv = results_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Results CSV",
                    data=csv,
                    file_name=f"availability_check_{today.strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        else:
            # Show summary without running check
            if emails:
                st.info(f"Ready to check {len(emails)} accounts for platform: {selected_platform}")
            
            if selected_platform and orders_df is not None:
                st.subheader("📊 Platform Summary")
                platform_theaters = [theater for theater, platform in THEATER_PLATFORM_MAPPING.items() if platform == selected_platform]
                
                platform_orders = orders_df[orders_df['theater'].isin(platform_theaters)] if 'theater' in orders_df.columns else pd.DataFrame()
                
                if not platform_orders.empty:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("🎭 Theaters", len(platform_theaters))
                    with col2:
                        st.metric("🎫 Total Orders", len(platform_orders))
                    with col3:
                        unique_events = platform_orders['event'].nunique() if 'event' in platform_orders.columns else 0
                        st.metric("🎪 Unique Events", unique_events)

if __name__ == "__main__":
    main()