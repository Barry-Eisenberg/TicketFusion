# from project folder, using your venv python
& .venv\Scripts\python.exe - <<'PY'
import inspect, db
try:
    sig = inspect.signature(db.upsert_rows)
    print("signature:", sig)
    print("-" * 40)
    print(inspect.getsource(db.upsert_rows))
except Exception as e:
    print("Error:", e)
PY