import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import toml
import io
from io import BytesIO
import openpyxl
from tempfile import NamedTemporaryFile

st.title("🎫 TicketFusion - Import Test")
st.write("If you can see this, all imports work in Streamlit Cloud!")

try:
    # Test basic functionality
    df = pd.DataFrame({'test': [1, 2, 3]})
    st.write("✅ Pandas works")

    # Test plotly
    fig = px.line(df, x='test', y='test')
    st.write("✅ Plotly works")

    # Test datetime
    now = datetime.now()
    st.write(f"✅ Datetime works: {now.strftime('%Y-%m-%d')}")

    st.success("All imports and basic functionality working!")

except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    st.code(str(e))

st.sidebar.header("Import Test Complete")
st.sidebar.write("✅ All dependencies loaded successfully")