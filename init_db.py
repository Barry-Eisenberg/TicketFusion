from db import get_engine

engine = get_engine()
with engine.begin() as conn:
    conn.exec_driver_sql("""
    CREATE TABLE IF NOT EXISTS sheet_facts (
      row_hash TEXT PRIMARY KEY,
      order_id INTEGER,
      customer_name TEXT,
      amount REAL,
      status TEXT,
      ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
print("sheet_facts created/verified in:", engine.url)