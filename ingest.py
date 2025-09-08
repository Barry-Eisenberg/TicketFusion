# ingest.py
import os
import sys
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
import difflib
import json
import inspect
import hashlib

# replace the previous single import with a guarded import and fallbacks
from db import get_engine, init_db, upsert_rows
try:
    from db import with_row_hash, normalize_df
except Exception:
    with_row_hash = None
    normalize_df = None

from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import os
from dotenv import load_dotenv
import numpy as np

# add this so BASE_DIR is available for DB_URL and relative paths
BASE_DIR = Path(__file__).resolve().parent

# load .env from project root so os.getenv(...) works
load_dotenv(BASE_DIR / ".env")

# Allow overriding the header row index via .env (GOOGLE_SHEETS_HEADER_ROW, 1-based)
try:
    HEADER_ROW_IDX = int(os.getenv("GOOGLE_SHEETS_HEADER_ROW", "4")) - 1
except Exception:
    HEADER_ROW_IDX = 3

DOC_ID = os.getenv("GOOGLE_SHEETS_DOC_ID")
TAB = os.getenv("GOOGLE_SHEETS_TAB", "Orders")
CREDS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
DB_URL = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data.db'}")

# resolve relative creds file path
if not os.path.isabs(CREDS_FILE):
    CREDS_FILE = str((BASE_DIR / CREDS_FILE).resolve())

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logging.info(f"Using credentials: {CREDS_FILE}")

if not os.path.exists(CREDS_FILE):
    logging.error(f"Service account key not found at: {CREDS_FILE}")
    sys.exit(1)

# Replace the static SCHEMA_MAP with a desired schema and a builder that matches sheet headers.
# DESIRED_SCHEMA: key = normalized_name, value = (list_of_possible_sheet_headers, pandas_dtype)
DESIRED_SCHEMA = {
    "sold_date": (["Sold Date"], "datetime64[ns]"),
    "event_date": (["Event Date"], "datetime64[ns]"),
    "time": (["Time"], "string"),
    "site": (["Site"], "string"),
    "order_id": (["Order ID"], "Int64"),
    "confirm_id": (["Confirm ID"], "string"),
    "revenue": (["Revenue"], "float"),
    "cost": (["Cost"], "float"),
    "cnt": (["CNT"], "Int64"),
    "cc": (["CC"], "string"),
    "purch_by": (["Purch By"], "string"),
    "purch_date": (["Purch Date"], "datetime64[ns]"),
    "trans_by": (["Trans By"], "string"),
    "trans_date": (["Trans Date"], "datetime64[ns]"),
    "email": (["Email"], "string"),
    "event": (["Event"], "string"),
    "theater": (["Theater"], "string"),
    "section": (["Section"], "string"),
    "row": (["Row"], "string"),
    "venue": (["Venue"], "string"),
    "notes": (["Notes"], "string"),
    "ingested_at": (["Ingested At", "Ingested", "Timestamp"], "datetime64[ns]"),
}

FUZZY_CUTOFF = 0.6  # 0.0-1.0, increase to require closer matches

def build_schema_map(actual_headers):
    """
    Build SCHEMA_MAP: maps actual sheet header -> (normalized_name, dtype)
    Uses exact match against alternatives first, then difflib fuzzy matching.
    """
    actual = [str(h).strip() for h in actual_headers]
    mapping = {}
    used_actual = set()

    for norm_name, (alternatives, dtype) in DESIRED_SCHEMA.items():
        found = None
        # exact match (case-sensitive and case-insensitive)
        for alt in alternatives:
            if alt in actual:
                found = alt
                break
        if not found:
            for alt in alternatives:
                alt_lower = alt.lower()
                for h in actual:
                    if h.lower() == alt_lower:
                        found = h
                        break
                if found:
                    break
        # fuzzy match fallback (try each alternative separately)
        if not found:
            for alt in alternatives:
                candidates = difflib.get_close_matches(alt, actual, n=1, cutoff=FUZZY_CUTOFF)
                if not candidates:
                    continue
                candidate = candidates[0]
                # special-case: do not match a very short header like "Time"
                # to a longer alternative like "Ingested At" / "Timestamp"
                if alt.lower().find("ingest") >= 0 or alt.lower().find("timestamp") >= 0:
                    if candidate.strip().lower() == "time":
                        # skip this fuzzy match (likely wrong)
                        continue
                found = candidate
                break

        if found:
            mapping[found] = (norm_name, dtype)
            used_actual.add(found)
        else:
            # no header found for this normalized field; create mapping so we still create the column later
            mapping[f"__missing__:{norm_name}"] = (norm_name, dtype)

    # Print helpful diagnostics
    logging.info("Detected sheet headers: %s", actual)
    logging.info("Built schema map (header -> (normalized, dtype)):")
    for k, v in mapping.items():
        logging.info("  %s -> %s", k, v)

    # Also warn about any actual headers not used
    unused = [h for h in actual if h not in used_actual]
    if unused:
        logging.info("Unused actual headers (not matched to DESIRED_SCHEMA): %s", unused)

    return mapping

# Schema map: left = sheet header, right = (normalized_name, pandas_dtype)
SCHEMA_MAP = {
    "Order ID": ("order_id", "Int64"),
    "Customer Name": ("customer_name", "string"),
    "Amount": ("amount", "float"),
    "Status": ("status", "string"),
    "Ingested At": ("ingested_at", "datetime64[ns]"),
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _extract_sheet_key(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", s)
    if m:
        return m.group(1)
    return s.strip("/")


def fetch_sheet(doc_id: str, tab: str) -> pd.DataFrame:
    """
    Fetch a native Google Sheet tab and return a DataFrame.
    Heuristics:
      - find the row that looks like a header (contains expected header keywords
        or has many non-empty cells) and promote it to DataFrame columns.
      - fallback to first row if detection fails.
    """
    logging.debug(f"[DEBUG] DOC_ID: {doc_id}")
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)

    key = _extract_sheet_key(str(doc_id or ""))

    try:
        ws = gc.open_by_key(key).worksheet(tab)
    except gspread.exceptions.SpreadsheetNotFound:
        if str(doc_id or "").lower().startswith("http") or "docs.google.com" in str(doc_id or "").lower():
            ws = gc.open_by_url(str(doc_id)).worksheet(tab)
        else:
            raise RuntimeError("Spreadsheet not found. Confirm GOOGLE_SHEETS_DOC_ID and that the service account has Viewer access.")
    except gspread.exceptions.APIError as e:
        raise RuntimeError("Sheets API error: ensure the ID points to a Google Sheet and the service account is shared with it.") from e

    data = ws.get_all_values()
    if not data:
        return pd.DataFrame()

    # If env override present, use it
    if HEADER_ROW_IDX is not None and 0 <= HEADER_ROW_IDX < len(data):
        header_idx = HEADER_ROW_IDX
        logging.info("Using HEADER_ROW_IDX override: %d", header_idx)
    else:
        # existing heuristic detection...
        expected_keywords = {
            "order", "sold", "event", "date", "revenue", "email", "confirm", "site",
            "purch", "trans", "ticket", "venue", "section", "row", "cost", "profit"
        }

        header_idx = None
        for i, row in enumerate(data):
            lower = [str(c).strip().lower() for c in row]
            # count cells that contain any expected keyword
            keyword_matches = sum(1 for cell in lower if any(k in cell for k in expected_keywords))
            non_empty = sum(1 for cell in lower if cell)
            # choose row if it has multiple expected keywords OR many non-empty cells
            if keyword_matches >= 2 or non_empty >= 6:
                header_idx = i
                logging.info("Detected header row at index %d: %s", header_idx, row)
                break

        if header_idx is None:
            # fallback: pick first non-empty row as header
            for i, row in enumerate(data):
                if any(cell for cell in row):
                    header_idx = i
                    logging.info("Fallback header row at index %d", header_idx)
                    break
        if header_idx is None:
            header_idx = 0

    header_row = data[header_idx]
    header = [str(h).strip() if h and str(h).strip() != "" else f"_col{j}" for j, h in enumerate(header_row)]
    rows = data[header_idx + 1 :]

    df = pd.DataFrame(rows, columns=header)

    # Normalize column names to stripped strings and make unique (preserve existing logic)
    raw_cols = [str(c).strip() for c in df.columns]
    seen = {}
    cols = []
    for c in raw_cols:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)
    df.columns = cols

    logging.info("Final column names used: %s", df.columns.tolist())
    return df


def enforce_schema_and_prepare(df: pd.DataFrame, schema_map: dict) -> pd.DataFrame:
    """
    Now accepts schema_map (actual_header -> (normalized_name, dtype)).
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # run project normalization (promotes headers, trims cells, etc.)
    try:
        df = normalize_df(df)
    except Exception:
        df = df.applymap(lambda x: str(x).strip() if pd.notna(x) else x)

    # Build rename map from actual header -> normalized name
    rename_map = {}
    for actual_header, (norm_name, dtype) in schema_map.items():
        if actual_header.startswith("__missing__"):
            continue
        if actual_header in df.columns and norm_name not in df.columns:
            rename_map[actual_header] = norm_name
    if rename_map:
        df = df.rename(columns=rename_map)

    # Ensure normalized names exist as columns (create missing as null)
    for _, (norm_name, dtype) in schema_map.items():
        # skip the placeholder keys
        if norm_name not in df.columns:
            df[norm_name] = pd.NA

    # Ensure ingested_at exists and is a timestamp if missing
    if "ingested_at" not in df.columns or df["ingested_at"].isna().all():
        now = pd.Timestamp.utcnow().tz_localize(None)
        df["ingested_at"] = now

    # Coerce types best-effort according to schema_map values (use norm_names)
    # Build unique set of norm_name->dtype
    norm_types = {}
    for _, (norm_name, dtype) in schema_map.items():
        norm_types[norm_name] = dtype

    # --- ADDED: clean currency/number strings so coercion works (strip $, commas, parentheses) ---
    import re
    for dst, dtype in norm_types.items():
        if dst in df.columns and dtype in ("float", "Int64"):
            # convert to str, strip common currency characters, then coerce
            df[dst] = df[dst].astype("string").fillna("").str.replace(r"[^\d\.\-]", "", regex=True)
            # keep empty strings as NaN for numeric conversion
            df.loc[df[dst] == "", dst] = pd.NA
    # --- end added block ---

    for dst, dtype in norm_types.items():
        if dst in df.columns:
            try:
                if dtype == "datetime64[ns]":
                    df[dst] = pd.to_datetime(df[dst], errors="coerce")
                else:
                    df[dst] = df[dst].astype(dtype)
            except Exception:
                if dtype in ("float", "Int64"):
                    df[dst] = pd.to_numeric(df.get(dst), errors="coerce")
                    if dtype == "Int64":
                        try:
                            df[dst] = df[dst].astype("Int64")
                        except Exception:
                            pass
                else:
                    df[dst] = df[dst].astype("string")

    # Compute row hash using project helper (append column 'row_hash')
    try:
        if with_row_hash:
            df = with_row_hash(df)
        else:
            raise RuntimeError("with_row_hash not available")
    except Exception:
        # stable SHA1 of the joined row values
        def _sha1_of_row(row):
            s = "|".join("" if v is None else str(v) for v in row)
            return hashlib.sha1(s.encode("utf-8")).hexdigest()
        df["row_hash"] = df.apply(lambda r: _sha1_of_row(r.values), axis=1)

    return df


def write_schema_suggestion(schema_map: dict, out_dir: Path = BASE_DIR):
    """
    Write two files:
      - schema_suggestion.json : { normalized_name: { matched_header, dtype } }
      - suggested_schema.py     : Python literal SCHEMA_MAP to paste into code
    """
    suggestion = {}
    for actual_header, (norm_name, dtype) in schema_map.items():
        if actual_header.startswith("__missing__"):
            # actual header not found
            suggestion[norm_name] = {"matched_header": None, "dtype": dtype}
        else:
            suggestion[norm_name] = {"matched_header": actual_header, "dtype": dtype}

    # JSON file
    json_path = out_dir / "schema_suggestion.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(suggestion, fh, indent=2, ensure_ascii=False)

    # Python file with SCHEMA_MAP style literal (header -> (norm, dtype))
    py_map = {}
    for actual_header, (norm_name, dtype) in schema_map.items():
        if actual_header.startswith("__missing__"):
            # prefer writing normalized_name as placeholder key
            py_map[norm_name] = (norm_name, dtype)
        else:
            py_map[actual_header] = (norm_name, dtype)

    py_path = out_dir / "suggested_schema.py"
    with open(py_path, "w", encoding="utf-8") as fh:
        fh.write("# Suggested SCHEMA_MAP (paste into ingest.py or app.py and edit as needed)\n")
        fh.write("SCHEMA_MAP = {\n")
        for k, v in py_map.items():
            fh.write(f"    {json.dumps(k)}: ({json.dumps(v[0])}, {json.dumps(v[1])}),\n")
        fh.write("}\n")

    logging.info("Wrote schema suggestion to: %s and %s", json_path, py_path)


def main():
    if not DOC_ID:
        logging.error("GOOGLE_SHEETS_DOC_ID not set in .env")
        sys.exit(1)

    # create engine object and pass it to init_db (init_db expects an Engine)
    engine = get_engine(DB_URL)
    init_db(engine)

    logging.info(f"[DEBUG] DOC_ID: {DOC_ID}")
    raw = fetch_sheet(DOC_ID, TAB)
    if raw is None or raw.empty:
        logging.info("No rows fetched from sheet.")
        return

    # build schema map from actual headers
    schema_map = build_schema_map(raw.columns)

    # AUTO-WRITE suggestion files for manual review / edit
    try:
        write_schema_suggestion(schema_map)
    except Exception as e:
        logging.warning("Failed to write schema suggestion files: %s", e)

    df = enforce_schema_and_prepare(raw, schema_map)

    # (removed legacy mapping for customer_name/amount/status)

    # Continue preparing rows for DB upsert...
    # Prepare rows to upsert: convert timestamps to ISO or native objects depending on DB layer
    # We convert pandas Timestamp to Python datetime to be safe for SQLAlchemy
    # Convert pandas Timestamp -> python datetime (safest for SQLAlchemy)
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].apply(lambda x: x.to_pydatetime() if pd.notna(x) else None)

    # Ensure missing values become None and numpy/pandas scalars become native Python scalars
    df = df.where(pd.notna(df), None)

    rows = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            # treat pandas/np missing as None
            if pd.isna(v):
                clean[k] = None
                continue
            # pandas/np scalar -> python native
            if isinstance(v, (np.generic,)):
                try:
                    clean[k] = v.item()
                except Exception:
                    clean[k] = v
                continue
            # leave datetimes and strings intact
            clean[k] = v
        rows.append(clean)

    # Upsert into DB table 'sheet_facts' using expected signature: upsert_rows(engine, rows)
    try:
        upsert_rows(engine, rows)
        logging.info("Upserted %d rows to sheet_facts", len(rows))
    except Exception as e:
        logging.exception("Failed to upsert rows: %s", e)
        raise

if __name__ == "__main__":
    main()
