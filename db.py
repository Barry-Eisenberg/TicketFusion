from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    Text,
    Float,
    DateTime,
    insert,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func
import logging
import numpy as np
import pandas as pd
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_URL = f"sqlite:///{BASE_DIR / 'data.db'}"

metadata = MetaData()

# Define the canonical table used by the project
sheet_facts = Table(
    "sheet_facts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("row_hash", Text, nullable=False, unique=True),
    Column("sold_date", DateTime),
    Column("event_date", DateTime),
    Column("time", Text),
    Column("site", Text),
    Column("order_id", Integer),
    Column("confirm_id", Text),
    Column("revenue", Float),
    Column("cost", Float),
    Column("cnt", Integer),
    Column("cc", Text),
    Column("purch_by", Text),
    Column("purch_date", DateTime),
    Column("trans_by", Text),
    Column("trans_date", DateTime),
    Column("email", Text),
    Column("event", Text),
    Column("theater", Text),
    Column("section", Text),
    Column("row", Text),
    Column("venue", Text),
    Column("notes", Text),
    Column("ingested_at", DateTime, server_default=func.current_timestamp()),
)


def get_engine(db_url: str | None = None) -> Engine:
    """
    Create and return an SQLAlchemy Engine. Do NOT run any DB operations at import time.
    """
    url = db_url or DEFAULT_DB_URL
    return create_engine(url, future=True)


def init_db(engine: Engine) -> None:
    """
    Create required tables if they don't exist.
    """
    metadata.create_all(engine)


def upsert_rows(engine: Engine, rows: List[Dict[str, Any]]) -> int:
    """
    Generic upsert that derives columns from rows (list[dict]) and upserts
    each row using row_hash as the conflict key.
    """
    if not rows:
        return 0

    # union of keys across rows; keep deterministic order
    cols = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                cols.append(k)

    if "row_hash" not in cols:
        raise ValueError("each row must include 'row_hash'")

    # build SQL
    cols_quoted = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    update_cols = [c for c in cols if c != "row_hash"]
    if update_cols:
        update_sql = ", ".join(f'"{c}" = excluded."{c}"' for c in update_cols)
    else:
        update_sql = '"row_hash" = excluded."row_hash"'  # no-op update

    sql = (
        f'INSERT INTO sheet_facts ({cols_quoted}) VALUES ({placeholders}) '
        f'ON CONFLICT(row_hash) DO UPDATE SET {update_sql}'
    )

    def _clean_value(v):
        # pandas / numpy missing -> None
        if pd.isna(v):
            return None
        # pandas Timestamp -> python datetime
        if hasattr(v, "to_pydatetime"):
            try:
                return v.to_pydatetime()
            except Exception:
                pass
        # numpy datetime64 -> python datetime
        if isinstance(v, np.datetime64):
            return pd.to_datetime(v).to_pydatetime()
        # numpy / pandas scalar -> python native
        if isinstance(v, (np.generic,)):
            try:
                return v.item()
            except Exception:
                return v
        return v

    with engine.begin() as conn:
        for r in rows:
            # order params to match cols list; None for missing keys
            params = tuple(_clean_value(r.get(c)) for c in cols)
            conn.exec_driver_sql(sql, params)

    return len(rows)
