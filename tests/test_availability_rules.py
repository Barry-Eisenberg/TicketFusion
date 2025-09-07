import pandas as pd
import pytest
from datetime import timedelta

from check_account_availability import check_email_availability


def make_orders(rows):
    return pd.DataFrame(rows)


def test_rule1_active_tickets_violation():
    today = pd.Timestamp.utcnow()
    email = "user1@example.com"
    # existing active tickets = 8
    orders = make_orders([
        {
            "email": email,
            "cnt": 8,
            "event": "E1",
            "theater": "T1",
            "event_date": today + pd.Timedelta(days=1),
            "sold_date": today - pd.Timedelta(days=10),
            "ingested_at": today - pd.Timedelta(days=10),
        }
    ])

    ok, reasons = check_email_availability(email, orders, today, event=None, theater=None, event_date=None, cnt_new=1)
    assert not ok
    assert any("Rule1" in r for r in reasons)


def test_rule2_six_month_window_violation_with_prospective():
    today = pd.Timestamp.utcnow()
    email = "user2@example.com"
    # 11 existing tickets within 6 months
    rows = []
    for i in range(11):
        rows.append({
            "email": email,
            "cnt": 1,
            "event": f"E{i}",
            "theater": "T",
            "event_date": today + pd.Timedelta(days=30 + i),
            "sold_date": today - pd.Timedelta(days=10 * i),
            "ingested_at": today - pd.Timedelta(days=10 * i),
        })
    orders = make_orders(rows)

    # prospective 2 tickets sold today -> window total becomes 13 (>12)
    ok, reasons = check_email_availability(email, orders, today, event="NewEvent", theater="T", event_date=today + pd.Timedelta(days=100), cnt_new=2, sold_date_new=today)
    assert not ok
    assert any("Rule2" in r for r in reasons)


def test_rule3_multiple_event_dates_violation():
    today = pd.Timestamp.utcnow()
    email = "user3@example.com"
    # existing single purchase for event/theater on one date
    orders = make_orders([
        {
            "email": email,
            "cnt": 1,
            "event": "ConcertX",
            "theater": "MainHall",
            "event_date": today + pd.Timedelta(days=10),
            "sold_date": today - pd.Timedelta(days=5),
            "ingested_at": today - pd.Timedelta(days=5),
        }
    ])

    # prospective purchase for same event/theater but different event_date -> violation
    prospective_event_date = today + pd.Timedelta(days=20)
    ok, reasons = check_email_availability(email, orders, today, event="ConcertX", theater="MainHall", event_date=prospective_event_date, cnt_new=1, sold_date_new=today)
    assert not ok
    assert any("Rule3" in r for r in reasons)


def test_available_when_no_violations():
    today = pd.Timestamp.utcnow()
    email = "free@example.com"
    orders = make_orders([])
    ok, reasons = check_email_availability(email, orders, today, event=None, theater=None, event_date=None, cnt_new=1)
    assert ok
    assert reasons == []
