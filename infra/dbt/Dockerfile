FROM python:3.11-slim

WORKDIR /dbt

# System dependencies (Postgres libs, build tools, git optional)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libpq-dev build-essential git && \
    rm -rf /var/lib/apt/lists/*

# Install dbt-postgres (this will also install dbt-core + dbt-adapters
# in compatible versions)
RUN pip install --no-cache-dir dbt-postgres
