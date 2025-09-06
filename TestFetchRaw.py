from ingest import fetch_sheet, DOC_ID, TAB
import pandas as pd, traceback, sys

pd.set_option("display.max_columns", 200)
pd.set_option("display.width", 200)

try:
    raw = fetch_sheet(DOC_ID, TAB)
    print("Columns:", list(raw.columns))
    print("\nFirst 10 rows:")
    print(raw.head(10).to_string(index=False))
except Exception as e:
    print("ERROR running fetch_sheet:", e, file=sys.stderr)
    traceback.print_exc()