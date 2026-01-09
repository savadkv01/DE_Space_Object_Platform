FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libpq-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY infra/ingestion/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy all service code
COPY services /app/services

ENV PYTHONPATH=/app
