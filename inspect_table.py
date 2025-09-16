from db import get_engine
from sqlalchemy import inspect, text
import pandas as pd

engine = get_engine()
insp = inspect(engine)
table = "sheet_facts"
print("DB URL:", engine.url)
print("Tables:", insp.get_table_names())
if table not in insp.get_table_names():
    raise SystemExit(f"{table} not found")

cols = [c["name"] for c in insp.get_columns(table)]
print("Columns:", cols)

with engine.connect() as conn:
    # count rows
    total = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    print("Total rows:", total)

    # non-null count per column (safe)
    for c in cols:
        cnt = conn.execute(text(f"SELECT COUNT([{c}]) FROM {table} WHERE [{c}] IS NOT NULL")).scalar()
        print(f"  {c:20s} non-null: {cnt}")

    # show first 5 rows as pandas DataFrame for quick inspection
    df = pd.read_sql(f"SELECT * FROM {table} LIMIT 5", conn)
    print("\nSample rows:")
    print(df.head().to_string(index=False))