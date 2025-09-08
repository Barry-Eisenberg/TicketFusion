import os
from dotenv import load_dotenv
from difflib import get_close_matches
from google.oauth2.service_account import Credentials
import gspread
from sqlalchemy import create_engine, inspect
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DOC_ID = os.getenv("GOOGLE_SHEETS_DOC_ID")
TAB = os.getenv("GOOGLE_SHEETS_TAB", "Orders")
HEADER_ROW = int(os.getenv("GOOGLE_SHEETS_HEADER_ROW", "1"))
SA_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data.db'}")

# Edit this list if your app expects different header names
EXPECTED_HEADERS = [
    "Order ID",
    "Customer Name",
    "Amount",
    "Status",
    "Ingested At",
]

print("Using sheet:", DOC_ID, "tab:", TAB, "header row:", HEADER_ROW)
print("Service account file:", SA_FILE)
print("DB_URL:", DB_URL)
print()

# Fetch header row from Google Sheets
creds = Credentials.from_service_account_file(
    SA_FILE,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"]
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(DOC_ID)
ws = sh.worksheet(TAB)
headers = ws.row_values(HEADER_ROW)
print("Headers found on row", HEADER_ROW, ":")
for i, h in enumerate(headers, start=1):
    print(f"  {i:2d}. '{h}'")
print()

# Compare to expected
print("Expected headers:")
for h in EXPECTED_HEADERS:
    ok = h in headers
    matches = get_close_matches(h, headers, n=3, cutoff=0.6)
    status = "OK" if ok else "MISSING"
    print(f" - {h:20s} : {status}", end="")
    if not ok and matches:
        print("  (close matches: " + ", ".join(f"'{m}'" for m in matches) + ")")
    else:
        print()
print()

# Show DB table columns for sheet_facts
engine = create_engine(DB_URL, future=True)
insp = inspect(engine)
if "sheet_facts" in insp.get_table_names():
    cols = [c["name"] for c in insp.get_columns("sheet_facts")]
    print("DB table 'sheet_facts' columns:", cols)
else:
    print("Table 'sheet_facts' not found in DB.")