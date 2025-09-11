#!/usr/bin/env bash
set -euo pipefail

# If GOOGLE_SERVICE_ACCOUNT_JSON env var exists, write it to /app/service_account.json and set GOOGLE_APPLICATION_CREDENTIALS
if [ -n "${GOOGLE_SERVICE_ACCOUNT_JSON:-}" ]; then
  echo "Writing service account JSON from env var to /app/service_account.json"
  printf '%s' "$GOOGLE_SERVICE_ACCOUNT_JSON" > /app/service_account.json
  export GOOGLE_APPLICATION_CREDENTIALS=/app/service_account.json
fi

# If GOOGLE_APPLICATION_CREDENTIALS env var points to a secret in Secret Manager (starts with secret://), fetch it
if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [[ "$GOOGLE_APPLICATION_CREDENTIALS" == secret://* ]]; then
  # Format: secret://projects/PROJECT/secrets/SECRET/versions/VERSION  OR secret://SECRET_NAME
  SECRET_REF=${GOOGLE_APPLICATION_CREDENTIALS#secret://}
  echo "Fetching secret $SECRET_REF from Secret Manager"
  # If gcloud is available, attempt to access Secret Manager
  if command -v gcloud >/dev/null 2>&1; then
    # Try to resolve to full resource name
    if [[ "$SECRET_REF" == projects/* ]]; then
      FULL_NAME="$SECRET_REF"
    else
      # assume project is set in env
      FULL_NAME="projects/${GCP_PROJECT:-}/secrets/$SECRET_REF/versions/latest"
    fi
    gcloud secrets versions access latest --secret="$SECRET_REF" --format='get(payload.data)' | tr '_-' '/+' | base64 --decode > /app/service_account.json
    export GOOGLE_APPLICATION_CREDENTIALS=/app/service_account.json
  else
    echo "gcloud not found; cannot fetch secret. Ensure GOOGLE_SERVICE_ACCOUNT_JSON is set or that GOOGLE_APPLICATION_CREDENTIALS points to a file inside the container."
  fi
fi

# Ensure a PORT is set for Cloud Run compatibility (default 8080)
export PORT="${PORT:-8080}"

# Helpful Streamlit env defaults
export STREAMLIT_SERVER_HEADLESS="${STREAMLIT_SERVER_HEADLESS:-true}"

# Ensure the local SQLite schema exists (non-fatal)
if command -v python >/dev/null 2>&1; then
  echo "Ensuring local SQLite schema exists (data.db -> /app/data.db)"
  # run a tiny one-off python snippet to create tables if missing
  python - <<'PY' || true
from db import get_engine, init_db
try:
    init_db(get_engine())
    print('DB init: OK')
except Exception as e:
    print('DB init: skipped/failure:', e)
PY
fi

# Run the requested command.
# If the Dockerfile uses a shell-form CMD (a single string) we need to run
# it through a shell so expansions like ${PORT:-8080} are evaluated and the
# command is parsed into argv correctly. Using `bash -lc` preserves the
# original behavior when CMD is provided as an array as well.
if [ "$#" -eq 0 ]; then
  echo "No command provided to entrypoint; exiting." >&2
  exit 0
fi

# Join all args into a single command string and run via bash -lc so
# environment variable expansions (e.g. ${PORT:-8080}) work when CMD is
# supplied in shell form by the Dockerfile.
CMD_STR="$*"
exec bash -lc "$CMD_STR"
