FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . /app

ENV STREAMLIT_SERVER_HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Use the port Cloud Run provides (default 8080)
EXPOSE 8080

# Copy entrypoint that can materialize service account JSON from an env var
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
# Use shell form so the PORT env var is expanded at container runtime. Falls back to 8080.
CMD streamlit run availability_app.py --server.port ${PORT:-8080} --server.address 0.0.0.0
