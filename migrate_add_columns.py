from db import get_engine
from sqlalchemy import inspect

engine = get_engine()
insp = inspect(engine)

table_name = "sheet_facts"
if table_name not in insp.get_table_names():
    print(f"{table_name} not found in DB. Run init_db() or create table first.")
    raise SystemExit(1)

existing = {col["name"] for col in insp.get_columns(table_name)}
wanted = {
    "order_id": "INTEGER",
    "customer_name": "TEXT",
    "amount": "REAL",
    "status": "TEXT",
    "ingested_at": "DATETIME DEFAULT (CURRENT_TIMESTAMP)"
}

to_add = {k: v for k, v in wanted.items() if k not in existing}
if not to_add:
    print("No columns to add. Schema already up-to-date.")
else:
    print("Adding columns:", ", ".join(to_add.keys()))
    with engine.begin() as conn:
        for col, sql_type in to_add.items():
            sql = f'ALTER TABLE {table_name} ADD COLUMN {col} {sql_type}'
            print("Executing:", sql)
            conn.exec_driver_sql(sql)

print("Migration complete.")

# show final schema
insp = inspect(engine)
print("Final columns:", [c["name"] for c in insp.get_columns(table_name)])