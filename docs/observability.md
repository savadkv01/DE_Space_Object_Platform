# Logging, Error Handling & Observability

## Logging

- Standardize on **Python logging** with structured messages:
  - JSON format **or**
  - Key-value pairs

- Every job (ingestion, Spark, Airflow task) must log:
  - Run ID / correlation ID
  - Source and target
  - Record counts
  - Execution duration
  - Errors and failure reasons

---

## Error Handling

### Retry Strategy

Explicit retry mechanisms are required for:

- **API calls**
  - Exponential backoff
- **Kafka operations**
- **Database writes**
  - Handle transient failures gracefully

### Idempotency

- All jobs must be **idempotent**
- Use:
  - Natural keys **or**
  - Unique constraints
- Prevent duplicate records when jobs are re-run

---

## Observability

### Metrics Definition (Pre-Implementation)

Define and agree on key metrics before implementation:

- Ingestion throughput
- Error counts
- Kafka consumer lag
- Airflow DAG duration
- Data quality statistics

### Metrics Collection (Planned)

- **Prometheus** will scrape exporters for:
  - Kafka
  - Postgres
  - Node (host metrics)
  - Optional: Spark

- Custom metrics emitted by:
  - Ingestion jobs
  - Spark transformations

### Dashboards (Planned)

- **Grafana dashboards** focused on:
  - Pipeline health
  - Infrastructure health
  - Failure detection and trend analysis

---

# Observability Overview (Draft)

## Logging

- Python logging across all services
- Structured logs (JSON or key-value)
- Run-level correlation using `run_id`

## Metrics (Planned)

- Prometheus exporters:
  - Postgres
  - Kafka
  - Node
- Custom application-level metrics from ingestion and Spark jobs

## Dashboards (Planned)

- Grafana dashboards for:
  - Pipeline performance
  - Infrastructure metrics

---

## Pipeline Run Tracking

Pipeline executions are tracked in the metadata table:

### `meta.pipeline_run`

**Fields:**
- `pipeline_name`
- `status`
- `records_processed`
- `error_message`
- `timestamps`

### Usage in Batch Ingestion

- Each execution of:
  - `nasa-neo-batch`
  - `celestrak-batch`
- Inserts one row into `meta.pipeline_run`

### Example Query

```sql
SELECT
  pipeline_name,
  start_time,
  status,
  records_processed,
  error_message
FROM meta.pipeline_run
ORDER BY start_time DESC
LIMIT 20;
