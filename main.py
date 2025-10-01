import streamlit as st
import pandas as pd

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
    ["Home", "Test Analytics", "Test Availability"]
)

if app_choice == "Home":
    st.header("Welcome to TicketFusion")
    st.write("This is a simplified version for deployment testing.")
    st.write("Once deployed, we'll configure Google Sheets integration.")
    
    # Test data display
    st.subheader("Test Data")
    test_data = pd.DataFrame({
        'Theater': ['Theater A', 'Theater B', 'Theater C'],
        'Revenue': [1000, 1500, 2000],
        'Cost': [500, 750, 1000]
    })
    st.dataframe(test_data)
    
elif app_choice == "Test Analytics":
    st.header("Analytics (Test Mode)")
    st.write("Analytics functionality will be enabled after Google Sheets configuration.")
    
    # Sample chart
    import plotly.express as px
    test_data = pd.DataFrame({
        'Theater': ['Theater A', 'Theater B', 'Theater C'],
        'Revenue': [1000, 1500, 2000]
    })
    fig = px.bar(test_data, x='Theater', y='Revenue', title='Sample Revenue Data')
    st.plotly_chart(fig)
    
elif app_choice == "Test Availability":
    st.header("Availability Checker (Test Mode)")
    st.write("Availability checking will be enabled after Google Sheets configuration.")
    
    # Test form
    theater = st.selectbox("Select Theater", ["Theater A", "Theater B", "Theater C"])
    if st.button("Test Analysis"):
        st.success(f"Analysis for {theater} would run here with Google Sheets data.")