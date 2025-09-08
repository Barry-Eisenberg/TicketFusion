from db import get_engine
from sqlalchemy import inspect
from pathlib import Path
import shutil
import datetime

BACKUP_PATH = Path(__file__).resolve().parent / "data.db.bak"

engine = get_engine()
insp = inspect(engine)
table = "sheet_facts"
if table not in insp.get_table_names():
    raise SystemExit(f"{table} not found in DB")

# desired full column list (includes existing names + new sheet fields)
desired = [
    "row_hash",
    "sold_date",
    "event_date",
    "time",
    "site",
    "order_id",
    "confirm_id",
    "revenue",
    "cost",
    "cnt",
    "cc",
    "purch_by",
    "purch_date",
    "trans_by",
    "trans_date",
    "email",
    "event",
    "theater",
    "section",
    "row",
    "venue",
    "notes",
    "customer_name",
    "amount",
    "status",
    "ingested_at",
]

# SQL types for desired columns
types = {
    "row_hash": "TEXT PRIMARY KEY",
    "sold_date": "TEXT",
    "event_date": "TEXT",
    "time": "TEXT",
    "site": "TEXT",
    "order_id": "INTEGER",
    "confirm_id": "TEXT",
    "revenue": "REAL",
    "cost": "REAL",
    "cnt": "INTEGER",
    "cc": "TEXT",
    "purch_by": "TEXT",
    "purch_date": "TEXT",
    "trans_by": "TEXT",
    "trans_date": "TEXT",
    "email": "TEXT",
    "event": "TEXT",
    "theater": "TEXT",
    "section": "TEXT",
    "row": "TEXT",
    "venue": "TEXT",
    "notes": "TEXT",
    "customer_name": "TEXT",
    "amount": "REAL",
    "status": "TEXT",
    "ingested_at": "DATETIME DEFAULT (CURRENT_TIMESTAMP)",
}

# Backup DB file (if sqlite file available)
try:
    db_file = engine.url.database
    if db_file:
        shutil.copy2(db_file, BACKUP_PATH)
        print("Backup created at:", BACKUP_PATH)
except Exception as e:
    print("Warning: failed to backup DB file:", e)

existing_cols = {c["name"] for c in insp.get_columns(table)}
print("Existing columns:", sorted(existing_cols))

with engine.begin() as conn:
    # create new table
    cols_sql = ",\n  ".join(f"{col} {types.get(col,'TEXT')}" for col in desired)
    conn.exec_driver_sql(f"CREATE TABLE IF NOT EXISTS {table}_new (\n  {cols_sql}\n);")
    # build select list: use existing column name when present, else NULL
    select_exprs = []
    for col in desired:
        if col in existing_cols:
            select_exprs.append(col)
        else:
            select_exprs.append(f"NULL AS {col}")
    select_sql = ", ".join(select_exprs)
    insert_cols = ", ".join(desired)
    print("Copying data into new table...")
    conn.exec_driver_sql(f"INSERT INTO {table}_new ({insert_cols}) SELECT {select_sql} FROM {table};")
    print("Swapping tables...")
    conn.exec_driver_sql(f"DROP TABLE {table};")
    conn.exec_driver_sql(f"ALTER TABLE {table}_new RENAME TO {table};")
    print("Migration complete.")