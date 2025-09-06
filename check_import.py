import traceback, sys
try:
    from google.oauth2.service_account import Credentials
    print("IMPORT_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)