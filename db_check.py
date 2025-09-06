from pathlib import Path
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

BASE = Path(r"C:\Users\bmeis\Dropbox\Barry\Filing Cabinet\BizVentures\Ventures\TicketFusion\Product\TF_WorkflowAutomationTool")
load_dotenv(BASE / ".env")

db = os.getenv("DB_URL")
print("DB_URL:", db)

e = create_engine(db, future=True)
insp = inspect(e)
tables = insp.get_table_names()
print("Tables:", tables)

if "sheet_facts" in tables:
    with e.begin() as c:
        n = c.execute(text("SELECT COUNT(*) FROM sheet_facts")).scalar_one()
        print("sheet_facts rows:", n)
