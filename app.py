# app.py
import os
import pandas as pd
from sqlalchemy import create_engine, inspect
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# page config must be set before other Streamlit calls
st.set_page_config(page_title="Google Sheets Analytics", layout="wide")
st.title("📊 Google Sheets Analytics")

DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data.db'}")
engine = create_engine(DB_URL, future=True)

# PRAGMA tuning for SQLite
with engine.begin() as conn:
    conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")

st.caption(f"Using database: {DB_URL}")

# Optional: fail early with a clear message if the table isn't there
inspector = inspect(engine)
if "sheet_facts" not in inspector.get_table_names():
    st.error("Table 'sheet_facts' not found in this database. Make sure ingest.py wrote to the same DB_URL shown above.")
    st.stop()

# Define your real schema mapping here.
# Key = column name in DB (or Google Sheet header), value = (normalized_name, pandas_dtype)
SCHEMA_MAP = {
    "Order ID": ("order_id", "Int64"),
    "Customer Name": ("customer_name", "string"),
    "Amount": ("amount", "float"),
    "Status": ("status", "string"),
    "Ingested At": ("ingested_at", "datetime64[ns]"),
}

@st.cache_data(ttl=60)
def load_data():
    df = pd.read_sql("SELECT * FROM sheet_facts ORDER BY id DESC LIMIT 100000", engine)

    # Map sheet headers to normalized names
    rename_map = {}
    for src, (dst, dtype) in SCHEMA_MAP.items():
        if src in df.columns:
            rename_map[src] = dst
    if rename_map:
        df = df.rename(columns=rename_map)

    # Coerce dtypes where possible
    for src, (dst, dtype) in SCHEMA_MAP.items():
        if dst in df.columns:
            try:
                if dtype == "datetime64[ns]":
                    df[dst] = pd.to_datetime(df[dst], errors="coerce")
                else:
                    df[dst] = df[dst].astype(dtype)
            except Exception:
                if dtype in ("float", "Int64"):
                    df[dst] = pd.to_numeric(df.get(dst), errors="coerce")
                    if dtype == "Int64":
                        df[dst] = df[dst].astype("Int64")
                else:
                    df[dst] = df[dst].astype("string")

    # Ensure ingested_at is datetime if present
    if "ingested_at" in df.columns:
        df["ingested_at"] = pd.to_datetime(df["ingested_at"], errors="coerce")

    return df

df = load_data()
st.write(f"Rows loaded: {len(df)}")

# Normalized column names to use in UI
col1_name = "customer_name"
col2_name = "status"
col3_name = "amount"

col1, col2 = st.columns(2)
with col1:
    term = st.text_input(f"Filter {col1_name} contains")
with col2:
    term2 = st.text_input(f"Filter {col2_name} equals")

q = df.copy()
if term and col1_name in q.columns:
    q = q[q[col1_name].str.contains(term, case=False, na=False)]
if term2 and col2_name in q.columns:
    q = q[q[col2_name] == term2]

st.dataframe(q, use_container_width=True)

# Rows ingested per day
if "ingested_at" in q.columns:
    tmp = q.copy()
    tmp["ingested_at"] = pd.to_datetime(tmp["ingested_at"], errors="coerce")
    daily = (
        tmp.dropna(subset=["ingested_at"])
           .groupby(tmp["ingested_at"].dt.date)
           .size()
           .reset_index(name="rows")
           .sort_values("ingested_at")
           .set_index("ingested_at")
    )
    st.subheader("Rows ingested per day")
    st.bar_chart(daily["rows"])
else:
    st.caption("Note: 'ingested_at' not found. Ensure ingest.py writes it (DEFAULT CURRENT_TIMESTAMP).")

# Example KPIs and charts (use normalized names)
st.subheader("Example KPIs")
if col3_name in q.columns:
    st.metric(f"Distinct {col3_name} values", int(q[col3_name].nunique()))
else:
    st.metric(f"Distinct {col3_name} values", 0)

st.subheader(f"Counts by {col2_name}")
if col2_name in q.columns:
    counts = q.groupby(col2_name).size().reset_index(name="count").sort_values("count", ascending=False)
    st.bar_chart(counts.set_index(col2_name))
else:
    st.caption(f"Column '{col2_name}' not found.")
