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

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from db import get_engine, init_db, upsert_rows
from transform import normalize_df, with_row_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Allow overriding the header row index via .env (GOOGLE_SHEETS_HEADER_ROW, 0-based)
HEADER_ROW_IDX = None
try:
    v = os.getenv("GOOGLE_SHEETS_HEADER_ROW")
    if v is not None and str(v).strip() != "":
        HEADER_ROW_IDX = int(v)
        logging.info("Using GOOGLE_SHEETS_HEADER_ROW from .env: %d", HEADER_ROW_IDX)
except Exception:
    HEADER_ROW_IDX = None

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
    "order_id": (["Order ID", "OrderID", "Order #", "Order_Num"], "Int64"),
    "customer_name": (["Customer Name", "Customer", "Client", "Client Name"], "string"),
    "amount": (["Amount", "Total", "Sale Amount", "Price"], "float"),
    "status": (["Status", "State"], "string"),
    "ingested_at": (["Ingested At", "Ingested", "Timestamp", "Created At"], "datetime64[ns]"),
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
        # fuzzy match fallback (choose best actual header)
        if not found:
            candidates = difflib.get_close_matches(" ".join(alternatives), actual, n=1, cutoff=FUZZY_CUTOFF)
            if candidates:
                found = candidates[0]

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
        df = with_row_hash(df)
    except Exception:
        df["row_hash"] = df.astype(str).sum(axis=1).apply(lambda s: str(abs(hash(s))))

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

    # Prepare rows to upsert: convert timestamps to ISO or native objects depending on DB layer
    # We convert pandas Timestamp to Python datetime to be safe for SQLAlchemy
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].apply(lambda x: x.to_pydatetime() if pd.notna(x) else None)

    rows = df.to_dict(orient="records")

    # Upsert into DB table 'sheet_facts' using expected signature: upsert_rows(engine, rows)
    try:
        upsert_rows(engine, rows)
        logging.info("Upserted %d rows to sheet_facts", len(rows))
    except Exception as e:
        logging.exception("Failed to upsert rows: %s", e)
        raise

if __name__ == "__main__":
    main()
