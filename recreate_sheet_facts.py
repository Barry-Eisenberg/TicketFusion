from db import get_engine, init_db
eng = get_engine()
print('engine', eng.url)
with eng.begin() as conn:
    conn.exec_driver_sql('DROP TABLE IF EXISTS sheet_facts')
    print('dropped')
init_db(eng)
print('created')
