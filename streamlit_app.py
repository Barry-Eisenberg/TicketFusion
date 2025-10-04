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

def check_email_availability(email, orders, today, event=None, theater=None, event_date=None, cnt_new=1, sold_date_new=None):
    """
    Simplified availability checker without database dependencies
    """
    # Check if orders DataFrame is valid and has required columns
    if orders is None or orders.empty:
        return True, ["No order data available"]
    
    # Check for email column - try different possible names
    email_col = None
    for col in ['email', 'Email', 'EMAIL', 'Email Address', 'email_address']:
        if col in orders.columns:
            email_col = col
            break
    
    if email_col is None:
        return True, ["Email column not found in order data"]
    
    # Filter orders for this email
    try:
        user_orders = orders[orders[email_col].astype(str).str.lower().str.strip() == email.lower().strip()]
    except Exception:
        return True, ["Error filtering orders by email"]
    
    if user_orders.empty:
        return True, []
    
    reasons = []
    
    # Rule 1: No orders in the last 12 months
    sold_date_cols = ['sold_date', 'Sold Date', 'SOLD_DATE', 'sold_date_new']
    sold_col = None
    for col in sold_date_cols:
        if col in user_orders.columns:
            sold_col = col
            break
    
    if sold_col:
        try:
            twelve_months_ago = today - timedelta(days=365)
            # Convert to datetime if not already
            dates = pd.to_datetime(user_orders[sold_col], errors='coerce')
            recent_orders = dates[dates >= twelve_months_ago]
            if not recent_orders.empty:
                reasons.append("Has orders within last 12 months")
        except Exception:
            pass  # Skip this rule if date conversion fails
    
    # Rule 2: No orders for the same event (if event specified)
    if event:
        event_cols = ['event', 'Event', 'EVENT', 'Event Name']
        event_col = None
        for col in event_cols:
            if col in user_orders.columns:
                event_col = col
                break
        
        if event_col:
            try:
                same_event_orders = user_orders[user_orders[event_col].astype(str).str.strip() == event.strip()]
                if not same_event_orders.empty:
                    reasons.append(f"Already has orders for event: {event}")
            except Exception:
                pass  # Skip this rule if comparison fails
    
    # Rule 3: No multiple purchases for same (Event + Theater) on different dates
    if event and theater:
        event_cols = ['event', 'Event', 'EVENT', 'Event Name']
        theater_cols = ['theater', 'Theater', 'THEATER', 'Venue', 'venue']
        
        event_col = None
        theater_col = None
        
        for col in event_cols:
            if col in user_orders.columns:
                event_col = col
                break
        
        for col in theater_cols:
            if col in user_orders.columns:
                theater_col = col
                break
        
        if event_col and theater_col:
            try:
                same_event_theater = user_orders[
                    (user_orders[event_col].astype(str).str.strip() == event.strip()) &
                    (user_orders[theater_col].astype(str).str.strip() == theater.strip())
                ]
                if len(same_event_theater) > 0:
                    reasons.append(f"Already has orders for {event} at {theater}")
            except Exception:
                pass  # Skip this rule if comparison fails
    
    # If any rules failed, not available
    is_available = len(reasons) == 0
    return is_available, reasons

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_google_sheets_data():
    """Load data from Google Sheets with proper error handling"""
    try:
        # Get credentials from Streamlit secrets
        if "google_service_account" not in st.secrets:
            st.error("Google service account credentials not found in secrets. Please configure them in Streamlit Cloud.")
            return None
            
        if "GOOGLE_SHEETS_DOC_ID" not in st.secrets:
            st.error("Google Sheets document ID not found in secrets. Please configure GOOGLE_SHEETS_DOC_ID in Streamlit Cloud.")
            return None
            
        credentials_dict = dict(st.secrets["google_service_account"])
        doc_id = st.secrets["GOOGLE_SHEETS_DOC_ID"]
        
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
                # Get all values and convert to DataFrame
                values = worksheet.get_all_values()
                if values:
                    # First row as headers
                    headers = values[0]
                    
                    # Clean up headers: remove empty strings and handle duplicates
                    cleaned_headers = []
                    header_counts = {}
                    
                    for i, header in enumerate(headers):
                        # Replace empty headers with generic names
                        if not header or header.strip() == "":
                            header = f"Column_{i+1}"
                        else:
                            header = header.strip()
                        
                        # Handle duplicate headers by adding suffix
                        if header in header_counts:
                            header_counts[header] += 1
                            header = f"{header}_{header_counts[header]}"
                        else:
                            header_counts[header] = 0
                        
                        cleaned_headers.append(header)
                    
                    if len(values) > 1:
                        df = pd.DataFrame(values[1:], columns=cleaned_headers)
                        # Remove completely empty columns
                        df = df.loc[:, (df != '').any(axis=0)]
                        data[worksheet.title] = df
                    else:
                        data[worksheet.title] = pd.DataFrame(columns=cleaned_headers)
                else:
                    data[worksheet.title] = pd.DataFrame()
            except Exception as e:
                st.error(f"Error loading {worksheet.title}: {e}")
                data[worksheet.title] = pd.DataFrame()
        
        return data
        
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

def main():
    st.title("🎭 TicketFusion Dashboard")
    st.markdown("---")
    
    # Navigation
    app_choice = st.sidebar.selectbox(
        "Choose App", 
        ["Home", "Data Overview", "Account Availability Checker"],
        index=0
    )
    
    if app_choice == "Home":
        st.header("Welcome to TicketFusion Dashboard")
        st.write("""
        This dashboard provides tools for analyzing ticket sales data and checking account availability.
        
        **Available Features:**
        - **Data Overview**: View and analyze your ticket sales data
        - **Account Availability Checker**: Check if accounts are eligible for new purchases
        """)
        
    elif app_choice == "Data Overview":
        st.header("📊 Data Overview & Analytics")
        
        # Load data
        sheets_data = load_google_sheets_data()
        if sheets_data:
            # First show raw data in expandable sections
            st.subheader("📋 Raw Data")
            for sheet_name, df in sheets_data.items():
                with st.expander(f"📋 {sheet_name} ({len(df)} rows)"):
                    if not df.empty:
                        try:
                            # Display first 10 rows with error handling
                            display_df = df.head(10)
                            # Reset index to avoid any index-related issues
                            display_df = display_df.reset_index(drop=True)
                            st.dataframe(display_df, use_container_width=True)
                            st.write(f"Columns: {', '.join(df.columns)}")
                        except Exception as e:
                            st.error(f"Error displaying data for {sheet_name}: {e}")
                            st.write(f"Sheet has {len(df)} rows and {len(df.columns)} columns")
                            st.write(f"Columns: {', '.join(df.columns)}")
                    else:
                        st.info("No data available")
            
            # Add analytics if Orders data is available
            if 'Orders' in sheets_data and not sheets_data['Orders'].empty:
                st.subheader("📈 Analytics")
                orders_df = sheets_data['Orders'].copy()
                
                # Try to find date and venue columns
                date_cols = ['Sold Date', 'sold_date', 'Date', 'Event Date', 'event_date']
                venue_cols = ['Theater', 'theater', 'Venue', 'venue']
                event_cols = ['Event', 'event', 'Event Name', 'event_name']
                
                date_col = None
                venue_col = None
                event_col = None
                
                for col in date_cols:
                    if col in orders_df.columns:
                        date_col = col
                        break
                
                for col in venue_cols:
                    if col in orders_df.columns:
                        venue_col = col
                        break
                        
                for col in event_cols:
                    if col in orders_df.columns:
                        event_col = col
                        break
                
                # Show basic metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Orders", len(orders_df))
                with col2:
                    if venue_col:
                        unique_venues = orders_df[venue_col].nunique()
                        st.metric("Unique Venues", unique_venues)
                    else:
                        st.metric("Venues", "N/A")
                with col3:
                    if event_col:
                        unique_events = orders_df[event_col].nunique()
                        st.metric("Unique Events", unique_events)
                    else:
                        st.metric("Events", "N/A")
                
                # Charts if we have the right columns
                if venue_col:
                    st.subheader("Orders by Venue")
                    try:
                        venue_counts = orders_df[venue_col].value_counts().head(10)
                        if not venue_counts.empty:
                            import plotly.express as px
                            fig = px.bar(
                                x=venue_counts.values,
                                y=venue_counts.index,
                                orientation='h',
                                title="Top 10 Venues by Order Count"
                            )
                            fig.update_layout(xaxis_title="Order Count", yaxis_title="Venue")
                            st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error creating venue chart: {e}")
                
                if date_col:
                    st.subheader("Orders Over Time")
                    try:
                        # Convert dates and group by month
                        orders_df[date_col] = pd.to_datetime(orders_df[date_col], errors='coerce')
                        monthly_orders = orders_df.groupby(orders_df[date_col].dt.to_period('M')).size()
                        
                        if not monthly_orders.empty:
                            import plotly.express as px
                            fig = px.line(
                                x=monthly_orders.index.astype(str),
                                y=monthly_orders.values,
                                title="Orders by Month"
                            )
                            fig.update_layout(xaxis_title="Month", yaxis_title="Order Count")
                            st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error creating time series chart: {e}")
        else:
            st.error("Could not load data for analysis")
    
    elif app_choice == "Account Availability Checker":
        st.header("🎫 Account Availability Checker")
        st.write("Check ticket availability for specific events using the three availability rules")
        
        # Load theater-to-platform mapping - use fallback data since CSV may not be available in cloud
        THEATER_PLATFORM_MAPPING = {
            "Academy of Music at Kimmel": "Ensemble",
            "Marian Anderson Hall": "Ensemble", 
            "Miller Theather at Kimmel": "Ensemble",
            "Buell Theatre": "Denver Center",
            "The Marvin and Judi Wolf Theatre": "Denver Center",
            "Steinmetz Hall": "Dr Phillips", 
            "Walt Disney Theater": "Dr Phillips",
            "Kia Center": "Dr Phillips",
            "Des Moines Civic Center": "Des Moines Civic Center",
            "Abravanel Hall": "ArtTix",
            "Delta Hall": "ArtTix",
            "Eccles Theater": "ArtTix",
            "Janet Quinney Lawson Capitol Theatre": "ArtTix",
            "The Greek Theater": "Cal Performances",
            "Zellerbach Hall": "Cal Performances",
            "Helzberg Hall": "Kauffman Center",
            "Muriel Kauffman Theater": "Kauffman Center",
            "Merrill Auditorium": "PortTix",
            "Hawks Mainstage at Omaha Community Playhouse": "Ticketomaha",
            "Kiewit Concert Hall at Holland Performing Arts Center": "Ticketomaha",
            "Orpheum Theater": "Ticketomaha"
        }
        
        # Try to load from CSV if available, but don't fail if it's not
        try:
            mapping_df = pd.read_csv('TheaterMapping_v2.csv')
            # Create dictionary: Theater -> Venue Platform
            csv_mapping = {}
            for _, row in mapping_df.iterrows():
                theater_name = row['Theater'].strip()
                platform_name = row['Venue Platform'].strip()
                csv_mapping[theater_name] = platform_name
            # Update with CSV data if available
            THEATER_PLATFORM_MAPPING.update(csv_mapping)
            st.sidebar.info(f"📁 Loaded {len(csv_mapping)} additional mappings from CSV")
        except Exception:
            # CSV not available in cloud, use fallback mappings
            st.sidebar.info(f"🗺️ Using {len(THEATER_PLATFORM_MAPPING)} built-in theater mappings")
        
        # === Sidebar Controls ===
        st.sidebar.header("Prospective Purchase Details")
        
        # Load Google Sheets data
        sheets_data = load_google_sheets_data()
        
        if not sheets_data:
            st.error("Could not load Google Sheets data")
            return
        
        # Orders data processing
        orders_df = None
        if 'Orders' in sheets_data:
            orders_df = sheets_data['Orders'].copy()
            
            # Column mapping for Orders data
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
        
        # Platform dropdown (replaces theater dropdown)
        
        # Get events from orders data
        existing_events = []
        if orders_df is not None and 'event' in orders_df.columns:
            existing_events = sorted(orders_df['event'].dropna().astype(str).str.strip().unique().tolist())
        
        if selected_platform and THEATER_PLATFORM_MAPPING:
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
        
        # Fixed inputs for simplicity
        event_date = "2024-12-15"  # Default event date
        sold_date = "2024-11-15"   # Default sold date
        cnt = st.sidebar.number_input("Ticket Count", min_value=1, max_value=10, value=1)
        
        # Account data processing
        emails = []
        if 'Accounts' in sheets_data:
            df = sheets_data['Accounts']
            if len(df.columns) >= 3:
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
                    else:
                        emails = df[email_col].dropna().unique()
                    
                    emails = [e for e in emails if str(e).strip() != "" and "@" in str(e) and "." in str(e)]
            else:
                st.sidebar.error("Not enough columns found in Accounts data")
        else:
            st.sidebar.error("Accounts tab not found in Google Sheets data")
        
        # Today's date for calculations
        today = pd.Timestamp.now()
        
        # Display current settings
        st.write("### Current Settings")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Event", event if event else "Not selected")
        with col2:
            st.metric("Platform", selected_platform if selected_platform else "Not selected")
        with col3:
            st.metric("Available Emails", len(emails))
        
        # Availability rules explanation
        with st.expander("📋 Availability Rules"):
            st.write("**Rule 1:** No orders in the last 12 months")
            st.write("**Rule 2:** No existing orders for the same event")
            st.write("**Rule 3:** No multiple purchases for same (Event + Theater) on different event dates")
            
        # Get the venue platform for availability checking (it's the selected platform)
        venue_platform = selected_platform
        if venue_platform:
            st.write(f"**Availability Check:** Using venue platform **{venue_platform}**")
        
        # Show theaters in this platform
        if venue_platform and THEATER_PLATFORM_MAPPING:
            theaters_in_platform = [theater for theater, platform in THEATER_PLATFORM_MAPPING.items() if platform == venue_platform]
            st.write(f"**Platform includes theaters:** {', '.join(theaters_in_platform[:3])}{'...' if len(theaters_in_platform) > 3 else ''}")
        
        st.write(f"**Prospective Purchase:** {event or 'Any Event'} at {venue_platform or 'Any Platform'} on {event_date} ({cnt} ticket{'s' if cnt > 1 else ''})")
        
        # Check availability for each email
        if st.button("🔍 Check Availability", type="primary"):
            if not emails:
                st.warning("No emails to check. Please select a platform or ensure Accounts data is loaded.")
                return
                
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
                    cnt_new=cnt,
                    sold_date_new=pd.Timestamp(sold_date) if sold_date else None
                )
                
                results.append({
                    "email": email,
                    "available": is_available,
                    "reasons": "; ".join(reasons) if reasons else "Available",
                    "event": event or "N/A",
                    "theater": theater or "N/A",
                    "event_date": event_date,
                    "cnt": cnt
                })
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            # Convert results to DataFrame
            results_df = pd.DataFrame(results)
            
            # Display summary
            total_emails = len(results_df)
            available_count = len(results_df[results_df['available'] == True])
            unavailable_count = total_emails - available_count
            
            st.write("### 📊 Results Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Emails", total_emails)
            with col2:
                st.metric("Available", available_count, delta=f"{(available_count/total_emails*100):.1f}%")
            with col3:
                st.metric("Unavailable", unavailable_count, delta=f"{(unavailable_count/total_emails*100):.1f}%")
            
            # Display detailed results
            st.write("### 📋 Detailed Results")
            
            # Tabs for available vs unavailable
            tab1, tab2, tab3 = st.tabs(["✅ Available", "❌ Unavailable", "📊 All Results"])
            
            with tab1:
                available_df = results_df[results_df['available'] == True]
                if not available_df.empty:
                    st.dataframe(available_df[['email', 'event', 'theater']], use_container_width=True)
                    
                    # Download button for available emails
                    csv = available_df['email'].to_csv(index=False, header=False)
                    st.download_button(
                        label="📥 Download Available Emails",
                        data=csv,
                        file_name=f"available_emails_{venue_platform}_{event}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No available emails found.")
            
            with tab2:
                unavailable_df = results_df[results_df['available'] == False]
                if not unavailable_df.empty:
                    st.dataframe(unavailable_df[['email', 'reasons']], use_container_width=True)
                else:
                    st.info("All emails are available!")
            
            with tab3:
                st.dataframe(results_df, use_container_width=True)
                
                # Download all results
                csv_all = results_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download All Results",
                    data=csv_all,
                    file_name=f"availability_results_{venue_platform}_{event}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()