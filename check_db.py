from db import get_engine
from sqlalchemy import inspect
import pathlib, sys

engine = get_engine()
try:
    # show engine URL / file path
    url = getattr(engine, "url", None)
    print("engine.url:", url)
except Exception as e:
    print("Failed to read engine.url:", e)
insp = inspect(engine)
print("Tables in DB:", insp.get_table_names())
if "sheet_facts" in insp.get_table_names():
    cols = [c["name"] for c in insp.get_columns("sheet_facts")]
    print("sheet_facts columns:", cols)
else:
    print("sheet_facts not found")
# show physical file for sqlite (if available)
try:
    file_path = str(engine.url.database)
    print("SQLite file:", file_path)
    print("Exists on disk:", pathlib.Path(file_path).exists())
except Exception:
    pass