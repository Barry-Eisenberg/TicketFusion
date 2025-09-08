import sqlite3
from pathlib import Path
p = Path('data.db').resolve()
print('db file:', p)
conn = sqlite3.connect(p)
cur = conn.cursor()
cur.execute("PRAGMA table_info(sheet_facts)")
rows = cur.fetchall()
if not rows:
    print('sheet_facts: not found')
else:
    print('sheet_facts columns:')
    for r in rows:
        print(r)
conn.close()
