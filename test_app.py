import streamlit as st

st.title("🎫 TicketFusion - Test Deployment")
st.write("If you can see this, the deployment is working!")
st.info("✅ App deployed successfully - data loading issues can be fixed separately")

# Simple test to verify Streamlit works
if st.button("Test Button"):
    st.success("Button works!")

st.sidebar.header("Test Sidebar")
st.sidebar.write("Sidebar loads correctly")