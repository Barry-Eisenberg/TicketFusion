from db import get_engine
from datetime import datetime

def insert_samples():
    engine = get_engine()
    rows = [
        {
            'row_hash': 'r1',
            'email': 'alice@example.com',
            'cnt': 2,
            'event': 'Old Event',
            'theater': 'Main',
            'event_date': datetime(2024, 9, 1),
            'sold_date': datetime(2024, 8, 1),
        },
        {
            'row_hash': 'r2',
            'email': 'bob@example.com',
            'cnt': 5,
            'event': 'Another Event',
            'theater': 'Main',
            'event_date': datetime(2026, 1, 1),
            'sold_date': datetime(2025, 8, 1),
        },
        {
            'row_hash': 'r3',
            'email': 'carol@example.com',
            'cnt': 1,
            'event': 'Sample Event',
            'theater': 'Main',
            'event_date': datetime(2025, 9, 15),
            'sold_date': datetime(2025, 9, 1),
        },
    ]
    with engine.begin() as conn:
        for r in rows:
            # build param list matching columns in table; use INSERT OR REPLACE to upsert
            conn.exec_driver_sql(
                "INSERT OR REPLACE INTO sheet_facts (row_hash, email, cnt, event, theater, event_date, sold_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (r['row_hash'], r['email'], r['cnt'], r['event'], r['theater'], r['event_date'], r['sold_date'])
            )
    print('inserted sample rows')

if __name__ == '__main__':
    insert_samples()
