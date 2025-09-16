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
    "Sold Date": ("sold_date", "datetime64[ns]"),
    "Event Date": ("event_date", "datetime64[ns]"),
    "Time": ("time", "string"),
    "Site": ("site", "string"),
    "Order ID": ("order_id", "Int64"),
    "Confirm ID": ("confirm_id", "string"),
    "Revenue": ("revenue", "float"),
    "Cost": ("cost", "float"),
    "CNT": ("cnt", "Int64"),
    "CC": ("cc", "string"),
    "Purch By": ("purch_by", "string"),
    "Purch Date": ("purch_date", "datetime64[ns]"),
    "Trans By": ("trans_by", "string"),
    "Trans Date": ("trans_date", "datetime64[ns]"),
    "Email": ("email", "string"),
    "Event": ("event", "string"),
    "Theater": ("theater", "string"),
    "Section": ("section", "string"),
    "Row": ("row", "string"),
    "Venue": ("venue", "string"),
    "Notes": ("notes", "string"),
}

@st.cache_data(ttl=60)
def load_data():
    # Build a safe SELECT that only requests columns present in the DB
    inspector = inspect(engine)
    table_cols = [c["name"] for c in inspector.get_columns("sheet_facts")]
    desired = ["row_hash", "ingested_at"] + [dst for _, (dst, _) in SCHEMA_MAP.items()]
    cols = [c for c in desired if c in table_cols]
    if not cols:
        return pd.DataFrame(columns=desired)
    cols_sql = ", ".join(cols)
    df = pd.read_sql(f"SELECT {cols_sql} FROM sheet_facts ORDER BY ingested_at DESC LIMIT 100000", engine)

    # Coerce dtypes based on SCHEMA_MAP
    dst_dtype = {dst: dtype for _, (dst, dtype) in SCHEMA_MAP.items()}
    for col, dtype in dst_dtype.items():
        if col not in df.columns:
            continue
        try:
            if dtype == "datetime64[ns]":
                df[col] = pd.to_datetime(df[col], errors="coerce")
            elif dtype == "Int64":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            elif dtype == "float":
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = df[col].astype("string")
        except Exception:
            # best-effort coercion; ignore failures
            pass

    if "ingested_at" in df.columns:
        df["ingested_at"] = pd.to_datetime(df["ingested_at"], errors="coerce")

    return df

df = load_data()
st.write(f"Rows loaded: {len(df)}")

# Basic text filters and UI defaults (replace previous block)
col1, col2, col3 = st.columns(3)
with col1:
    term = st.text_input("Filter: text contains (applies to first textual column)")
with col2:
    term2 = st.text_input("Filter: exact match (applies to second categorical column)")
with col3:
    # Revenue range slider if revenue exists
    if "revenue" in df.columns and not df["revenue"].dropna().empty:
        rev_min = float(df["revenue"].min())
        rev_max = float(df["revenue"].max())
        rev_range = st.slider("Revenue range", rev_min, rev_max, (rev_min, rev_max))
    else:
        rev_range = None

# Determine sensible default columns for KPI and counts (safe/fallback)
possible_kpi_cols = ["customer_name", "purch_by", "trans_by", "email", "site", "event"]
possible_count_cols = ["status", "event", "site", "venue", "theater"]

def first_existing(candidates, dfcols):
    for c in candidates:
        if c in dfcols:
            return c
    return None

col3_name = first_existing(possible_kpi_cols, df.columns)
col2_name = first_existing(possible_count_cols, df.columns)

# Sold Date range filter if available
sold_from = sold_to = None
if "sold_date" in df.columns and not df["sold_date"].dropna().empty:
    sd_min = df["sold_date"].min().date()
    sd_max = df["sold_date"].max().date()
    sold_from, sold_to = st.date_input("Sold Date range", [sd_min, sd_max])

q = df.copy()
# Apply filters only if target columns exist
if term and col3_name:
    q = q[q[col3_name].astype(str).str.contains(term, case=False, na=False)]
if term2 and col2_name:
    q = q[q[col2_name].astype(str) == term2]
if rev_range and "revenue" in q.columns:
    q = q[q["revenue"].between(rev_range[0], rev_range[1])]
if sold_from and sold_to and "sold_date" in q.columns:
    q = q.dropna(subset=["sold_date"])
    q = q[(q["sold_date"].dt.date >= sold_from) & (q["sold_date"].dt.date <= sold_to)]

st.dataframe(q, use_container_width=True)

# Revenue time series (by Sold Date) if available
if "sold_date" in q.columns and "revenue" in q.columns and not q[["sold_date", "revenue"]].dropna().empty:
    rev_ts = q.dropna(subset=["sold_date", "revenue"]).groupby(q["sold_date"].dt.date)["revenue"].sum().reset_index()
    rev_ts["sold_date"] = pd.to_datetime(rev_ts["sold_date"])
    rev_ts = rev_ts.set_index("sold_date").sort_index()
    st.subheader("Revenue by Sold Date")
    st.line_chart(rev_ts["revenue"])

# Rows ingested per day
if "ingested_at" in q.columns:
    tmp = q.copy()
    tmp["ingested_at"] = pd.to_datetime(tmp["ingested_at"], errors="coerce")
    tmp = tmp.dropna(subset=["ingested_at"])
    if not tmp.empty:
        daily = (
            tmp.groupby(tmp["ingested_at"].dt.date)
               .size()
               .reset_index(name="rows")
        )
        # ensure a proper datetime index for plotting
        daily["ingested_at"] = pd.to_datetime(daily["ingested_at"])
        daily = daily.sort_values("ingested_at").set_index("ingested_at")
        st.subheader("Rows ingested per day")
        st.bar_chart(daily["rows"])
    else:
        st.caption("No ingested_at timestamps available to chart.")
else:
    st.caption("Note: 'ingested_at' not found. Ensure ingest.py writes it (DEFAULT CURRENT_TIMESTAMP).")

# Example KPIs and charts (use normalized names)
st.subheader("Example KPIs")
if col3_name and col3_name in q.columns and not q[col3_name].dropna().empty:
    st.metric(f"Distinct {col3_name} values", int(q[col3_name].nunique()))
else:
    st.metric("Distinct values", 0)

st.subheader(f"Counts by {col2_name or 'column'}")
if col2_name and col2_name in q.columns:
    counts = q.groupby(col2_name).size().reset_index(name="count").sort_values("count", ascending=False)
    if not counts.empty:
        counts = counts.set_index(col2_name)
        st.bar_chart(counts["count"])
    else:
        st.caption(f"No data to show for '{col2_name}'.")
else:
    st.caption(f"Column '{col2_name}' not found or not selected.")
