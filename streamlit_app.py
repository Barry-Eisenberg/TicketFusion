import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import toml

# Configure the page
st.set_page_config(
    page_title="TicketFusion Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)

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

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_google_sheets_data():
    """Load data from Google Sheets with proper error handling"""
    try:
        # Try to get credentials from Streamlit secrets, fallback to direct file read
        doc_id = None
        try:
            credentials_dict = dict(st.secrets["google_service_account"])
            doc_id = st.secrets["GOOGLE_SHEETS_DOC_ID"]
        except Exception:
            # Fallback: read directly from the ready file
            with open("STREAMLIT_SECRETS_READY.toml", "r") as f:
                secrets = toml.load(f)
                credentials_dict = dict(secrets["google_service_account"])
                doc_id = secrets["GOOGLE_SHEETS_DOC_ID"]
        
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
        
        st.sidebar.success(f"📊 Connected to Google Sheets")
        st.sidebar.info(f"Available sheets: {', '.join(worksheet_names)}")
        
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
                except Exception as header_error:
                    # If header issue, try alternative method
                    if "header row" in str(header_error).lower() and "not unique" in str(header_error).lower():
                        try:
                            # Get all values and create DataFrame manually
                            all_values = worksheet.get_all_values()
                            
                            # CORRECT HEADER ROWS:
                            # Accounts: ROW 1 (index 0)
                            # Orders: ROW 4 (index 3)
                            if worksheet.title == 'Accounts':
                                if all_values and len(all_values) > 1:
                                    headers = all_values[0]  # Row 1 (index 0) for Accounts
                                    data_rows = all_values[1:]  # Data starts from row 2
                                else:
                                    st.warning(f"⚠️ '{worksheet.title}' appears to be empty")
                                    continue
                            else:
                                # For Orders and other sheets: ROW 4
                                if all_values and len(all_values) > 4:
                                    headers = all_values[3]  # Row 4 (index 3) for Orders
                                    data_rows = all_values[4:]  # Data starts from row 5
                                else:
                                    st.warning(f"⚠️ '{worksheet.title}' appears to be empty")
                                    continue
                                
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
                        except Exception as fallback_error:
                            st.error(f"❌ Failed to load '{worksheet.title}': {fallback_error}")
                    else:
                        # For any other error, try manual loading with row 4 headers for Orders
                        try:
                            all_values = worksheet.get_all_values()
                            if worksheet.title == 'Orders' and all_values and len(all_values) > 4:
                                headers = all_values[3]  # Row 4 for Orders
                                data_rows = all_values[4:]
                                df = pd.DataFrame(data_rows, columns=headers)
                                data[worksheet.title] = df
                            else:
                                raise header_error
                        except:
                            st.error(f"❌ Failed to load '{worksheet.title}': {header_error}")
                            
            except Exception as e:
                st.error(f"Error loading {worksheet.title}: {e}")
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
    st.title("🎫 TicketFusion Dashboard")
    st.markdown("---")
    
    # Load data
    with st.spinner("Loading data from Google Sheets..."):
        sheets_data = load_google_sheets_data()

    # Sidebar navigation
    st.sidebar.title("Navigation")
    app_choice = st.sidebar.selectbox(
        "Choose an application:",
        ["Home", "Analytics", "Account Availability Checker"]
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
        with st.expander("📊 Data Status", expanded=False):
            if sheets_data:
                st.success(f"✅ Connected to Google Sheets - {len(sheets_data)} worksheets loaded")
                
                st.write("**Loaded sheets:**")
                for sheet_name, df in sheets_data.items():
                    st.write(f"• **{sheet_name}**: {len(df)} rows, {len(df.columns)} columns")
            else:
                st.error("❌ No data loaded")

    elif app_choice == "Analytics":
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
        
        # Load theater-to-platform mapping from CSV file FIRST
        THEATER_PLATFORM_MAPPING = {}
        try:
            mapping_df = pd.read_csv('TheaterMapping_v2.csv')
            # Create dictionary: Theater -> Venue Platform
            for _, row in mapping_df.iterrows():
                theater_name = row['Theater'].strip()
                platform_name = row['Venue Platform'].strip()
                THEATER_PLATFORM_MAPPING[theater_name] = platform_name
        except Exception as e:
            st.sidebar.error(f"❌ Could not load theater mappings: {e}")
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
            
            # Column mapping for Orders data (Row 4 headers, Column O=email, Column Q=theater)
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
        
        # Collapsible theater mappings (for reference)
        with st.sidebar.expander("🗺️ View Theater → Platform Mappings", expanded=False):
            mapping_items = list(THEATER_PLATFORM_MAPPING.items())[:10]
            for theater_name, platform_name in mapping_items:
                st.write(f"• {theater_name} → {platform_name}")
            if len(THEATER_PLATFORM_MAPPING) > 10:
                st.write(f"... and {len(THEATER_PLATFORM_MAPPING) - 10} more")
        
        # Get events from orders data (use the already processed orders_df from above)
        existing_events = []
        if orders_df is not None and 'event' in orders_df.columns:
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
            
            # Remove duplicates and sort
            platform_events = sorted(list(set(all_platform_events)))
            
            if platform_events:
                event_choice = st.sidebar.selectbox(
                    f"Events in {selected_platform}", 
                    options=platform_events
                )
            else:
                st.sidebar.warning(f"No events found for platform: {selected_platform}")
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
        event_date = datetime.now().date()
        sold_date = datetime.now().date()
        
        # Account data processing
        emails = []
        if sheets_data and 'Accounts' in sheets_data:
            df = sheets_data['Accounts'].copy()
            st.write(f"**Accounts Data** ({len(df)} records)")
            
            # Show what columns actually exist for debugging
            with st.expander("🔍 Debug: Available Columns"):
                for i, col in enumerate(df.columns):
                    sample_vals = df[col].dropna().unique()[:3] if not df[col].dropna().empty else []
                    st.write(f"Column {i}: '{col}' → Sample: {list(sample_vals)}")
            
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
        if st.sidebar.button("🎯 Check Availability", type="primary"):
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