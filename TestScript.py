# Save and run this one-off script (or insert temporarily)
from google.oauth2.service_account import Credentials
import json
print("Service account email from CREDS_FILE:")
print(json.load(open(r"c:\Users\bmeis\Dropbox\Barry\Filing Cabinet\BizVentures\Ventures\TicketFusion\Product\TF_WorkflowAutomationTool\service_account.json"))["client_email"])