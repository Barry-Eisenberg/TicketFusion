import pandas as pd
from check_account_availability import check_email_availability


def test_empty_orders_returns_available():
    today = pd.Timestamp.utcnow()
    email = "noone@example.com"
    orders = pd.DataFrame([])  # empty
    ok, reasons = check_email_availability(email, orders, today, event=None, theater=None, event_date=None, cnt_new=1)
    assert ok
    assert reasons == []
