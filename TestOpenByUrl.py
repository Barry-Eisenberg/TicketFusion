from google.oauth2.service_account import Credentials
import gspread
import os
from pathlib import Path

# Use environment variable or default path
CREDS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
doc_id = "10mBvp3OkctERgz1RaMIbOtTRKLqwuBFg"  # replace if needed
url = f"https://docs.google.com/spreadsheets/d/{doc_id}/edit"
try:
    sh = gc.open_by_url(url)
    print("Opened sheet:", sh.title)
except gspread.exceptions.APIError as e:
    print("APIError:", e)
    try:
        print("Response text:", e.response.text)
    except Exception:
        pass
except Exception as e:
    print("Other error:", e)