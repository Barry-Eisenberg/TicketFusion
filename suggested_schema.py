# Suggested SCHEMA_MAP (paste into ingest.py or app.py and edit as needed)
SCHEMA_MAP = {
    "order_id": ("order_id", "Int64"),
    "customer_name": ("customer_name", "string"),
    "amount": ("amount", "float"),
    "status": ("status", "string"),
    "ingested_at": ("ingested_at", "datetime64[ns]"),
}
