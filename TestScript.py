# Save and run this one-off script (or insert temporarily)
from google.oauth2.service_account import Credentials
import json
import os
from pathlib import Path

# Use environment variable or default path
service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
if Path(service_account_path).exists():
    print("Service account email from CREDS_FILE:")
    print(json.load(open(service_account_path))["client_email"])
else:
    print("Service account file not found")