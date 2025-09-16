"""check_account_availability.py

Find which emails from the "Accounts" tab are available for new purchases
based on existing orders persisted in the `sheet_facts` table and the rules:

1) No email should have more than 8 active tickets (sum of CNT) for events
   whose Event Date is today or in the future. If Event Date is in the past,
   CNT does not apply for active-count purposes.
2) No more than 12 tickets purchased for any email in any 6-month period
   (based on Sold Date).
3) An email cannot have purchases for the same (Event, Theater) on different
   event dates.

Usage: run from repo root. It reads DB via `db.get_engine()` and pulls the
Accounts tab via `ingest.fetch_sheet()` by default (requires .env/creds). You
can also point to a CSV of accounts via --accounts-csv.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import sys
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from ingest import fetch_sheet, DOC_ID as ENV_DOC_ID
from db import get_engine

# Prefer GOOGLE_SERVICE_ACCOUNT_JSON (set by deployment) or GOOGLE_APPLICATION_CREDENTIALS
# If GOOGLE_SERVICE_ACCOUNT_JSON contains JSON content, write it to /app/service_account.json
# If GOOGLE_APPLICATION_CREDENTIALS points to secret:// or is empty, we leave it to the container entrypoint or runtime.
import os
_gsa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if _gsa_json:
    try:
        # if the var looks like a Secret Manager resource (projects/...), pass-through to entrypoint behavior
        if _gsa_json.startswith("projects/") or _gsa_json.startswith("secret://"):
            # let entrypoint or runtime handle secret retrieval; export as GOOGLE_APPLICATION_CREDENTIALS-like value
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", _gsa_json)
        else:
            # assume it's raw JSON content; materialize to file
            target = Path("/app/service_account.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_gsa_json)
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(target))
    except Exception:
        # non-fatal; fall back to existing behavior
        pass


def load_accounts_from_sheet(doc_id: Optional[str], tab: str = "Accounts") -> pd.Series:
    key = doc_id or ENV_DOC_ID
    if not key:
        raise RuntimeError("No DOC_ID provided and GOOGLE_SHEETS_DOC_ID not set in .env")
    df = fetch_sheet(key, tab)
    if df is None or df.empty:
        return pd.Series(dtype="string")
    # find the email column (case-insensitive match)
    email_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("email", "e-mail", "account email"):
            email_col = c
            break
    if email_col is None:
        # fallback: pick first column that looks like an email in values
        candidates = list(df.columns)
        for c in candidates:
            sample = df[c].dropna().astype(str).head(20)
            if any("@" in s for s in sample):
                email_col = c
                break
    if email_col is None:
        raise RuntimeError("Could not detect an Email column in Accounts tab")
    emails = df[email_col].astype("string").dropna().str.strip().str.lower()
    emails = emails[emails != ""]
    return emails.drop_duplicates().reset_index(drop=True)


def load_orders_from_db(engine) -> pd.DataFrame:
    # Read relevant columns from sheet_facts
    cols = ["email", "cnt", "event", "theater", "event_date", "sold_date", "ingested_at"]
    with engine.connect() as conn:
        try:
            df = pd.read_sql(f"SELECT {', '.join(cols)} FROM sheet_facts", conn)
        except Exception:
            # fallback: read all and then subset
            df = pd.read_sql("SELECT * FROM sheet_facts", conn)
            df = df[[c for c in cols if c in df.columns]]

    # normalize
    for d in ("event_date", "sold_date", "ingested_at"):
        if d in df.columns:
            df[d] = pd.to_datetime(df[d], errors="coerce")
    if "cnt" in df.columns:
        df["cnt"] = pd.to_numeric(df["cnt"], errors="coerce").fillna(1).astype("Int64")
    else:
        df["cnt"] = 1
    df["email"] = df["email"].astype("string").str.strip().str.lower()
    return df


def check_email_availability(
    email: str,
    orders: pd.DataFrame,
    today: pd.Timestamp,
    event: Optional[str] = None,
    theater: Optional[str] = None,
    event_date: Optional[pd.Timestamp] = None,
    cnt_new: int = 1,
    sold_date_new: Optional[pd.Timestamp] = None,
) -> Tuple[bool, List[str]]:
    """Return (available, reasons)

    Assumptions documented in code comments and printed as reasons when
    applicable.
    """
    reasons: List[str] = []
    # Normalize incoming orders DataFrame: tests may pass an empty DataFrame with no columns
    if not isinstance(orders, pd.DataFrame):
        orders = pd.DataFrame(orders)
    orders = orders.copy()
    required_cols = ["email", "cnt", "event", "theater", "event_date", "sold_date", "ingested_at"]
    for c in required_cols:
        if c not in orders.columns:
            orders[c] = pd.Series(dtype="object")

    # Normalize common types used by the checks
    for dcol in ("event_date", "sold_date", "ingested_at"):
        orders[dcol] = pd.to_datetime(orders[dcol], errors="coerce")
    if "cnt" in orders.columns:
        orders["cnt"] = pd.to_numeric(orders["cnt"], errors="coerce").fillna(1).astype("Int64")
    else:
        orders["cnt"] = 1
    orders["email"] = orders["email"].astype("string").str.strip().str.lower()
    o = orders[orders["email"] == email].copy()

    # Rule 1: active tickets (event_date >= today) sum(cnt) + prospective cnt_new <= 8
    # Assumption: missing event_date on existing rows -> treat as active (CNT applies)
    if not o.empty:
        active_mask = (o["event_date"].isna()) | (o["event_date"].dt.date >= today.date())
        active_tickets_existing = int(o.loc[active_mask, "cnt"].sum()) if not o.loc[active_mask].empty else 0
    else:
        active_tickets_existing = 0

    # Determine if the prospective purchase counts as active: event_date missing or in future/today
    prospective_counts_as_active = False
    if event_date is None:
        # conservative: assume it would count as active
        prospective_counts_as_active = True
    else:
        prospective_counts_as_active = event_date.date() >= today.date()

    active_tickets = active_tickets_existing + (cnt_new if prospective_counts_as_active else 0)
    if active_tickets > 8:
        reasons.append(f"Rule1: active tickets including new={active_tickets} > 8")

    # Rule 2: no more than 12 tickets in any 6-month period (based on sold_date)
    # Implementation: sliding window over sold_date-sorted rows.
    # Assumption: missing sold_date -> treat as ingested_at if available, else today's date.
    s = o.copy()
    if s.empty:
        sold_window_violation = False
    else:
        if "sold_date" not in s.columns or s["sold_date"].isna().all():
            if "ingested_at" in s.columns and not s["ingested_at"].isna().all():
                s["sold_date"] = s["ingested_at"].fillna(pd.Timestamp(today))
            else:
                s["sold_date"] = pd.Timestamp(today)

        s = s.dropna(subset=["sold_date"]).sort_values("sold_date").reset_index(drop=True)
        sold_window_violation = False
        if not s.empty:
            dates = s["sold_date"].tolist()
            cnts = s["cnt"].astype(int).tolist()
            # include prospective purchase in the lists (use sold_date_new or today)
            sd_new = sold_date_new if sold_date_new is not None else pd.Timestamp(today)
            dates.append(sd_new)
            cnts.append(int(cnt_new))
            # two-pointer sliding window
            j = 0
            import pandas as _pd
            for i in range(len(dates)):
                start = dates[i]
                end = start + _pd.DateOffset(months=6)
                # move j forward while dates[j] < end
                total = 0
                k = i
                while k < len(dates) and dates[k] < end:
                    total += cnts[k]
                    k += 1
                if total > 12:
                    sold_window_violation = True
                    break
    if sold_window_violation:
        reasons.append("Rule2: >12 tickets within a 6-month window")

    # Rule 3: No multiple purchases for same event+theater on different event dates
    # For each (event, theater) group, check number of distinct event_date values > 1
    # Rule 3: No multiple purchases for same (event, theater) on different event dates.
    # If prospective (event, theater, event_date) provided, include it in the group and check.
    if not o.empty or (event and theater and event_date is not None):
        # build a DataFrame representing existing + prospective rows for grouping
        grp_df = o[["event", "theater", "event_date"]].copy()
        if event and theater and event_date is not None:
            grp_df = pd.concat([
                grp_df,
                pd.DataFrame({"event": [event], "theater": [theater], "event_date": [event_date]})
            ], ignore_index=True)

        grp = grp_df.groupby(["event", "theater"], dropna=False)
        for (ev, th), g in grp:
            if pd.isna(ev) or str(ev).strip() == "" or pd.isna(th) or str(th).strip() == "":
                continue
            unique_dates = g["event_date"].dropna().dt.normalize().unique()
            if len(unique_dates) > 1:
                reasons.append(f"Rule3: multiple event dates for event='{ev}' theater='{th}'")
                break

    available = len(reasons) == 0
    return available, reasons


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Check which account emails are available for purchase")
    p.add_argument("--doc-id", help="Google Sheets DOC_ID (defaults to .env GOOGLE_SHEETS_DOC_ID)")
    p.add_argument("--accounts-tab", default="Accounts", help="Accounts tab name")
    p.add_argument("--accounts-csv", help="Path to CSV with emails (column named 'email' or first column)")
    p.add_argument("--db-url", help="DB URL (sqlalchemy), defaults to .env/DB_URL or data.db")
    # prospective purchase flags
    p.add_argument("--event", help="Prospective Event name (string)")
    p.add_argument("--theater", help="Prospective Theater/Venue name (string)")
    p.add_argument("--event-date", help="Prospective Event Date (YYYY-MM-DD)")
    p.add_argument("--cnt", type=int, default=1, help="Prospective ticket count (default 1)")
    p.add_argument("--sold-date", help="Prospective Sold Date (YYYY-MM-DD)")
    args = p.parse_args(argv)

    today = pd.Timestamp.utcnow()

    # load accounts
    if args.accounts_csv:
        path = Path(args.accounts_csv)
        if not path.exists():
            print("Accounts CSV not found:", path)
            return 2
        df_acc = pd.read_csv(path)
        if "email" in df_acc.columns:
            emails = df_acc["email"].astype("string").dropna().str.strip().str.lower().drop_duplicates().reset_index(drop=True)
        else:
            emails = df_acc.iloc[:, 0].astype("string").dropna().str.strip().str.lower().drop_duplicates().reset_index(drop=True)
    else:
        emails = load_accounts_from_sheet(args.doc_id, args.accounts_tab)

    engine = get_engine(args.db_url)
    orders = load_orders_from_db(engine)

    # parse prospective inputs
    event = args.event
    theater = args.theater
    event_date = pd.to_datetime(args.event_date, errors="coerce") if args.event_date else None
    sold_date = pd.to_datetime(args.sold_date, errors="coerce") if args.sold_date else None
    cnt_new = int(args.cnt or 1)

    available = []
    unavailable = {}

    for e in emails:
        try:
            ok, reasons = check_email_availability(
                e,
                orders,
                today,
                event=event,
                theater=theater,
                event_date=event_date,
                cnt_new=cnt_new,
                sold_date_new=sold_date,
            )
        except Exception as ex:
            ok = False
            reasons = [f"error evaluating: {ex}"]
        if ok:
            available.append(e)
        else:
            unavailable[e] = reasons

    print("\nAvailable emails:")
    for e in available:
        print("  ", e)

    print('\nUnavailable emails (with reasons):')
    for e, r in unavailable.items():
        print("-", e)
        for reason in r:
            print("    -", reason)

    print(f"\nSummary: {len(available)} available, {len(unavailable)} unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
