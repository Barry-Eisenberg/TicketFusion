from db import get_engine
e = get_engine()
with e.begin() as conn:
    conn.exec_driver_sql("DELETE FROM sheet_facts")
print("deleted all rows")