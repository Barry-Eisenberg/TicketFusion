FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . /app

# Set environment variables
ENV STREAMLIT_SERVER_HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Simple direct command
CMD ["python", "-m", "streamlit", "run", "main.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
