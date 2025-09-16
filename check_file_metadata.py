import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()
creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"),
    scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"]
)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)
file_id = os.getenv("GOOGLE_SHEETS_DOC_ID")
meta = drive.files().get(fileId=file_id, fields="id,name,mimeType,owners,shared,permissions").execute()
print("File metadata:", meta)