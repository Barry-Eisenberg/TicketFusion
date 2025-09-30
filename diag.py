import os, sys, pathlib, traceback
from dotenv import load_dotenv

# Use current directory instead of hardcoded path
PROJECT_DIR = pathlib.Path(__file__).resolve().parent
print("Python:", sys.version)
print("Interpreter:", sys.executable)
print("Project exists:", PROJECT_DIR.exists())

# Load .env explicitly from the project folder
load_dotenv(PROJECT_DIR / ".env")

doc_id = os.getenv("GOOGLE_SHEETS_DOC_ID")
tab    = os.getenv("GOOGLE_SHEETS_TAB")
creds  = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
db_url = os.getenv("DB_URL")

print("ENV present? ->",
      {"GOOGLE_SHEETS_DOC_ID": bool(doc_id),
       "GOOGLE_SHEETS_TAB": bool(tab),
       "GOOGLE_APPLICATION_CREDENTIALS": bool(creds),
       "DB_URL": bool(db_url)})

if creds:
    creds_path = (PROJECT_DIR / creds) if not os.path.isabs(creds) else pathlib.Path(creds)
    print("Creds path:", creds_path, "Exists:", creds_path.exists())

def try_import(name):
    try:
        __import__(name)
        print(f"import {name}: OK")
    except Exception as e:
        print(f"import {name}: FAIL -> {e}")

for pkg in ["gspread", "google.oauth2.service_account", "pandas", "sqlalchemy"]:
    try_import(pkg)

# Optional: ping the sheet (comment out if creds/env missing)
try:
    if not (doc_id and tab and creds):
        raise RuntimeError("Skip sheet test: missing env")
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    cobj = Credentials.from_service_account_file(
        str((PROJECT_DIR / creds) if not os.path.isabs(creds) else creds),
        scopes=SCOPES
    )
    gc = gspread.authorize(cobj)
    ws = gc.open_by_key(doc_id).worksheet(tab)
    data = ws.get_all_values()
    print("Sheet reachable. Header:", (data[0] if data else None), "| rows(excl header):", max(len(data)-1, 0))
except Exception as e:
    print("Sheet test FAILED:")
    traceback.print_exc()
