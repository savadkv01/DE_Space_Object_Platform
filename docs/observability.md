Logging

Standardize on Python logging with structured messages (JSON or key-value).
Every job (ingestion / Spark / Airflow task) logs:
Run ID / correlation ID.
Source & target.
Record counts, durations, and errors.
Error Handling

Explicit retry strategy for:
API calls (backoff).
Kafka operations.
DB writes (transient failures).
Idempotent operations:
Use natural keys or unique constraints to avoid duplicates when re-running jobs.
Observability

Define which metrics we care about (even before implementing Prometheus):
Ingestion throughput, error counts, Kafka lag, DAG duration, data quality stats.
Plan for:
Prometheus to scrape exporters (Kafka, Postgres, node, maybe Spark).
Grafana dashboards focusing on pipeline health.



# Observability Overview (Draft)

- Logging:
  - Python logging in all services, JSON- or key-value style.
  - Run-level correlation using run_id.

- Metrics (planned):
  - Prometheus exporters for:
    - Postgres
    - Kafka
    - Node
  - Custom metrics from ingestion and Spark jobs.

- Dashboards (planned):
  - Grafana for pipeline and infra metrics.


Pipeline run tracking

meta.pipeline_run fields:

pipeline_name, status, records_processed, error_message, timestamps.
How it’s used by batch ingestion:

Each run of nasa-neo-batch / celestrak-batch inserts a row.
Example query:

SELECT pipeline_name, start_time, status, records_processed, error_message
FROM meta.pipeline_run
ORDER BY start_time DESC
LIMIT 20;