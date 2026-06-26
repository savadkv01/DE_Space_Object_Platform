# Batch Ingestion – Space Objects Data Platform

## Overview

Batch ingestion pulls data from external APIs on a scheduled basis and writes to the bronze layer.  
Both ingestors are orchestrated by Airflow DAGs and are fully idempotent.

---

## Class Hierarchy

```
BaseBatchIngestionJob (services/ingestion/base_ingestion.py)
├── NasaNeoBatchIngestionJob  (services/ingestion/nasa_neo/neo_batch_ingestor.py)
└── CelesTrakSatcatBatchIngestionJob (services/ingestion/celestrak/celestrak_batch_ingestor.py)
```

### BaseBatchIngestionJob

Provides:
- `run_id` generation (UUID)
- `meta.pipeline_run` lifecycle: insert on start, update on end
- Structured logging via `services/common/logging_utils.py`
- Abstract `execute()` method

### NasaNeoBatchIngestionJob

- **Source:** `https://api.nasa.gov/neo/rest/v1/feed?start_date=&end_date=&api_key=`
- **Target:** `bronze.nasa_neo_event_raw`
- **Lookback:** `default_lookback_days` from `config.yaml` (default: 1)
- **Chunking:** Requests split into ≤7-day windows (`MAX_DAYS_PER_REQUEST = 7`)
- **Retry:** `requests.adapters.HTTPAdapter` with `Retry(total=3, backoff_factor=1.5, status_forcelist=(429,500,502,503,504))`
- **Idempotency:** `INSERT ... ON CONFLICT (neo_id, close_approach_date_full, orbiting_body) DO NOTHING`

### CelesTrakSatcatBatchIngestionJob

- **Source:** `https://celestrak.org/pub/satcat.csv`
- **Target:** `bronze.celestrak_satcat_raw`
- **Group:** Configurable (`default_group: active`)
- **Retry:** Same pattern as NEO client
- **Idempotency:** Checks for existing `(snapshot_group, snapshot_date)` before any insert; returns 0 if already loaded

---

## Airflow Integration

Both ingestors accept `triggered_by`, `dag_id`, and `task_id` parameters that are passed through to `meta.pipeline_run`:

```python
# From neo_batch_dag.py
from ingestion.nasa_neo.neo_batch_ingestor import NasaNeoBatchIngestionJob

NasaNeoBatchIngestionJob(
    triggered_by="airflow",
    dag_id=context["dag"].dag_id,
    task_id=context["task"].task_id,
).execute()
```

---

## Configuration

`services/ingestion/nasa_neo/config.yaml`:
```yaml
batch:
  default_lookback_days: 1
  max_days_per_request: 7
  inter_request_delay_sec: 1.0
streaming:
  poll_interval_sec: 300
  kafka_topic: nasa_neo_raw
client:
  timeout_sec: 15
  retry_total: 3
  retry_backoff_factor: 1.5
```

`services/ingestion/celestrak/config.yaml`:
```yaml
batch:
  default_group: active
streaming:
  poll_interval_sec: 600
  kafka_topic: celestrak_satcat_raw
client:
  timeout_sec: 15
  retry_total: 3
  retry_backoff_factor: 1.5
```

---

## Error Handling

- API failures after retries raise exceptions → `meta.pipeline_run.status = 'failed'`
- Individual record parse errors are logged but do not abort the run
- DB write failures propagate up (no silent data loss)

---

## Adding a New Source

1. Create `services/ingestion/<source_name>/` with:
   - `config.yaml` — source configuration
   - `<source>_client.py` — HTTP client with retry session
   - `<source>_batch_ingestor.py` — extends `BaseBatchIngestionJob`
   - `<source>_stream_producer.py` — Kafka producer
   - `__init__.py`
2. Add the target table to `infra/postgres/init.sql`
3. Create a DAG in `airflow/dags/`
4. Add a service to `docker-compose.yml` under the ingestion image
