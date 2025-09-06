from google.oauth2.service_account import Credentials
import gspread, os, itertools
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CREDS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", str(BASE_DIR / "service_account.json"))
DOC_ID = os.getenv("GOOGLE_SHEETS_DOC_ID")
TAB = os.getenv("GOOGLE_SHEETS_TAB", "Orders")

creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
gc = gspread.authorize(creds)
sh = gc.open_by_key(DOC_ID) if not (DOC_ID and DOC_ID.startswith("http")) else gc.open_by_url(DOC_ID)
ws = sh.worksheet(TAB)
data = ws.get_all_values()

print(f"Total rows fetched: {len(data)}\n")

keywords = ["sold date", "order id", "email", "confirm id", "revenue", "event", "site", "ticket", "venue"]
matches = []

for i, row in enumerate(data):
    lower_cells = [str(c).strip().lower() for c in row]
    # match if any keyword appears in any cell
    if any(any(k in cell for k in keywords) for cell in lower_cells):
        matches.append(i)

if matches:
    print("Found candidate header rows at indices:", matches)
    for idx in matches:
        lo = max(0, idx - 3)
        hi = min(len(data), idx + 4)
        print(f"\n--- Context rows {lo}..{hi-1} (header candidate at {idx}) ---")
        for j in range(lo, hi):
            print(f"[{j:02d}] {data[j]}")
else:
    print("No candidate header rows matched keywords. Printing first 60 rows for inspection:\n")
    for i, row in enumerate(itertools.islice(data, 0, 60)):
        print(f"[{i:02d}] {row}")

print("\nIf you still don't see the header row, paste the output here.")