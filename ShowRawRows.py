from google.oauth2.service_account import Credentials
import gspread, os, itertools
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CREDS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", str(BASE_DIR / "service_account.json"))
DOC_ID = os.getenv("GOOGLE_SHEETS_DOC_ID")
TAB = os.getenv("GOOGLE_SHEETS_TAB", "Orders")

creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
gc = gspread.authorize(creds)
key = DOC_ID
if key and key.startswith("http"):
    sh = gc.open_by_url(key)
else:
    sh = gc.open_by_key(key)
ws = sh.worksheet(TAB)
data = ws.get_all_values()

print(f"Total rows fetched: {len(data)}\n")
for i, row in enumerate(itertools.islice(data, 0, 30)):  # show first 30 rows
    # join cells so you can see where header-like text appears
    print(f"[{i:02d}]  {row}")