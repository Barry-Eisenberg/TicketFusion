import os
from google.oauth2.service_account import Credentials
import gspread
from dotenv import load_dotenv
load_dotenv()

creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"]
)
gc = gspread.authorize(creds)
print("DOC_ID:", os.getenv("GOOGLE_SHEETS_DOC_ID"))
sh = gc.open_by_key(os.getenv("GOOGLE_SHEETS_DOC_ID"))
print("Worksheets:", [ws.title for ws in sh.worksheets()])