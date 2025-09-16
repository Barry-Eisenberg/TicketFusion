from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread
from pathlib import Path
import os
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DOC_ID = os.getenv("GOOGLE_SHEETS_DOC_ID")
TAB = os.getenv("GOOGLE_SHEETS_TAB", "Orders")
HEADER_ROW = int(os.getenv("GOOGLE_SHEETS_HEADER_ROW", "1"))
SA_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")

print("DOC_ID:", DOC_ID)
print("TAB:", TAB)
print("HEADER_ROW:", HEADER_ROW)
print("SA_FILE:", SA_FILE)
print()

creds = Credentials.from_service_account_file(
    SA_FILE,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"]
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(DOC_ID)
ws = sh.worksheet(TAB)

all_rows = ws.get_all_values()
print("Total rows fetched from sheet:", len(all_rows))
if len(all_rows) < HEADER_ROW:
    print(f"Header row {HEADER_ROW} is beyond fetched rows ({len(all_rows)}).")
    raise SystemExit(1)

header = all_rows[HEADER_ROW - 1]
data_rows = all_rows[HEADER_ROW:]  # rows after header_row
print("\nHeader row values (exact):")
for i, h in enumerate(header, start=1):
    print(f"  {i:2d}. '{h}' -> suggested db column '{h.strip().lower().replace(' ', '_')}'")

print("\nPreview of first 8 data rows (showing header->cell):")
for ridx, row in enumerate(data_rows[:8], start=1):
    d = { (header[i] if i < len(header) else f"col_{i+1}"): (cell if cell != "" else None)
         for i, cell in enumerate(row) }
    print(f"\nRow {ridx}:")
    for k, v in d.items():
        print(f"  {k!r}: {v!r}")

# counts of non-empty per header across first 500 rows
limit = min(len(data_rows), 500)
counts = Counter()
for row in data_rows[:limit]:
    for i, h in enumerate(header):
        v = row[i] if i < len(row) and row[i] != "" else None
        if v is not None:
            counts[h] += 1

print("\nNon-empty counts (first %d data rows):" % limit)
for h in header:
    print(f"  '{h}': {counts.get(h,0)}")

print("\nIf these headers and values look correct, the next step is to ensure ingest.py maps these exact header strings to the DB column names (order_id, customer_name, revenue/amount, etc.).")