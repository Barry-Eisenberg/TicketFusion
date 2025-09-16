import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data.db'}")
print("DB_URL:", DB_URL)

engine = create_engine(DB_URL, future=True)

with engine.begin() as conn:
    # raw SQL count
    total = conn.execute(text("SELECT COUNT(*) FROM sheet_facts")).scalar()
    distinct_ids = conn.execute(text("SELECT COUNT(DISTINCT id) FROM sheet_facts")).scalar()
    print("SQL COUNT(*) =", total)
    print("SQL COUNT(DISTINCT id) =", distinct_ids)

# read all rows with pandas (no ORDER/LIMIT)
df_all = pd.read_sql("SELECT * FROM sheet_facts", engine)
print("pandas read_sql rows:", len(df_all))

# show id stats and nulls
if "id" in df_all.columns:
    print("id min/max:", df_all["id"].min(), df_all["id"].max())
    print("id nulls:", df_all["id"].isna().sum())

# show how many rows survive your app's load_data transformations
from app import SCHEMA_MAP  # reuse mapping
df = df_all.copy()

# rename like app
rename_map = {src: dst for src, (dst, _) in SCHEMA_MAP.items() if src in df.columns}
if rename_map:
    df = df.rename(columns=rename_map)

# coerce similar to app (best-effort)
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

print("rows after app-like coercion:", len(df))

# show sample rows that might be problematic (e.g., many NaNs)
print("\nTop 5 rows:")
print(df_all.head().to_string(index=False))
print("\nRows with any all-null values in important columns:")
print(df[[c for _, (c, _) in SCHEMA_MAP.items() if c in df.columns]].isna().all(axis=1).sum())