# transform.py
import hashlib
import pandas as pd

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    # Rename to your canonical schema
    colmap = {
        df.columns[0]: "col1",
        df.columns[1]: "col2",
        df.columns[2]: "col3",
    }
    df = df.rename(columns=colmap)
    # Strip whitespace, coerce types, etc.
    for c in ["col1","col2","col3"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    return df[["col1","col2","col3"]]

def with_row_hash(df: pd.DataFrame) -> pd.DataFrame:
    def _h(row):
        s = "|".join([str(row.get(k,"")) for k in ["col1","col2","col3"]])
        return hashlib.sha256(s.encode("utf-8")).hexdigest()
    df["row_hash"] = df.apply(_h, axis=1)
    return df
