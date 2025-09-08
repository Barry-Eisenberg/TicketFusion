from db import get_engine
from sqlalchemy import text

engine = get_engine()
print("Using DB:", engine.url)

with engine.begin() as conn:
    # get current columns for sheet_facts
    info = conn.execute(text("PRAGMA table_info(sheet_facts)")).fetchall()
    cols = [row[1] for row in info]
    print("sheet_facts cols:", cols)

    # prefer to show these if present; fall back to first 5 columns
    preferred = ["row_hash", "order_id", "customer_name", "amount", "status", "ingested_at"]
    select_cols = [c for c in preferred if c in cols]
    if not select_cols:
        select_cols = cols[:5] if cols else ["row_hash"]

    q = f"SELECT {', '.join(select_cols)} FROM sheet_facts LIMIT 5"
    sample = conn.execute(text(q)).fetchall()
    total = conn.execute(text("SELECT COUNT(1) FROM sheet_facts")).scalar()

    print("sheet_facts rows:", total)
    print("Sample rows:")
    for row in sample:
        print(tuple(row))