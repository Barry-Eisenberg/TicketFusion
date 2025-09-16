from ingest import fetch_sheet, build_schema_map, enforce_schema_and_prepare, DOC_ID, TAB
import pandas as pd, json

raw = fetch_sheet(DOC_ID, TAB)
print("Raw columns:", list(raw.columns))
schema_map = build_schema_map(raw.columns)
print("\nBuilt schema_map (header -> (norm, dtype)):")
print(json.dumps(schema_map, indent=2))
df = enforce_schema_and_prepare(raw, schema_map)
print("\nPrepared DataFrame shape:", df.shape)
print("\nDtypes:")
print(df.dtypes)
print("\nNon-null counts (selected normalized cols):")
for col in df.columns:
    nn = int(df[col].notna().sum())
    if nn > 0:
        print(f"  {col:20s} non-null: {nn}")
print("\nSample prepared rows (first 3 as dicts):")
pd.set_option("display.max_columns", 200)
print(df.head(3).to_string(index=False))
print("\nFirst row dict:")
print(json.dumps(df.head(1).to_dict(orient='records')[0], default=str, indent=2))