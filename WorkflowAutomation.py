# db.py
from sqlalchemy import create_engine, text

def get_engine(db_url: str):
    return create_engine(db_url, future=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sheet_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_hash TEXT NOT NULL,
  ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- Example columns from your sheet:
  col1 TEXT,
  col2 TEXT,
  col3 TEXT
);
CREATE INDEX IF NOT EXISTS idx_sheet_facts_rowhash ON sheet_facts(row_hash);
"""

UPSERT_SQL = """
INSERT INTO sheet_facts (row_hash, col1, col2, col3)
SELECT :row_hash, :col1, :col2, :col3
WHERE NOT EXISTS (SELECT 1 FROM sheet_facts WHERE row_hash = :row_hash);
"""

def init_db(engine):
    with engine.begin() as conn:
        for stmt in SCHEMA_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

def upsert_rows(engine, rows):
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text(UPSERT_SQL), r)
