# Data Flow – Space Objects Data Platform

This document describes how data moves through the platform from source APIs to the gold analytics layer.

---

## Overview

```
External Sources
      │
      ▼
┌─────────────────────┐    ┌──────────────────────────┐
│  NASA NEO API       │    │  CelesTrak SATCAT API     │
│  (NeoWs REST)       │    │  (CSV endpoint)           │
└────────┬────────────┘    └─────────┬────────────────┘
         │                           │
    Batch/Stream               Batch/Stream
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────┐
│                   BRONZE LAYER                       │
│   bronze.nasa_neo_event_raw (JSONB fields)           │
│   bronze.celestrak_satcat_raw (parsed_record JSONB)  │
└────────────────────────┬────────────────────────────┘
                         │
                    Apache Spark
               (bronze_to_silver_*.py)
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                   SILVER LAYER                       │
│   silver.neo                   (NEO dimension)       │
│   silver.neo_close_approach    (approach facts)      │
│   silver.satcat_satellite      (satellite dimension) │
│   silver.satcat_orbit_snapshot (orbital facts)       │
└────────────────────────┬────────────────────────────┘
                         │
                        dbt
                  (gold models)
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                    GOLD LAYER                        │
│   gold.neo_daily_activity                            │
│   gold.neo_hazard_summary                            │
│   gold.ai_neo_features                               │
│   gold.ai_satcat_features                            │
│   gold.satcat_orbit_summary                          │
└─────────────────────────────────────────────────────┘
```

---

## Batch Ingestion

### NASA NEO Batch

- **Source:** `https://api.nasa.gov/neo/rest/v1/feed`
- **Schedule:** Daily (Airflow `neo_batch_dag`)
- **Ingestor:** `services/ingestion/nasa_neo/neo_batch_ingestor.py`
- **Target:** `bronze.nasa_neo_event_raw`
- **Idempotency:** `ON CONFLICT DO NOTHING` on `(neo_id, close_approach_date_full, orbiting_body)`
- **Lookback:** Configurable via `config.yaml` (`default_lookback_days: 1`)
- **Retry:** 3 attempts, 1.5× backoff, on 429/5xx status codes

### CelesTrak SATCAT Batch

- **Source:** `https://celestrak.org/pub/satcat.csv`
- **Schedule:** Daily (Airflow `celestrak_batch_dag`)
- **Ingestor:** `services/ingestion/celestrak/celestrak_batch_ingestor.py`
- **Target:** `bronze.celestrak_satcat_raw`
- **Idempotency:** Checks for existing `(snapshot_group, snapshot_date)` before insert
- **Output:** ~16,000–17,000 satellite records per snapshot

---

## Streaming Ingestion

### Kafka Topics

| Topic | Producer | Consumer |
|---|---|---|
| `nasa_neo_raw` | `services/ingestion/nasa_neo/neo_stream_producer.py` | `spark_jobs/streaming/neo_stream_to_bronze.py` |
| `celestrak_satcat_raw` | `services/ingestion/celestrak/celestrak_stream_producer.py` | `spark_jobs/streaming/celestrak_stream_to_bronze.py` |

- Producers poll source APIs periodically and publish JSON events to Kafka.
- Spark Structured Streaming consumes from Kafka and writes to bronze tables.
- Streaming health is monitored by `streaming_supervision_dag` every 10 minutes.

---

## Spark Transformations (Bronze → Silver)

### NEO Job (`bronze_to_silver_neo.py`)

1. Read `bronze.nasa_neo_event_raw` (JSONB fields)
2. Parse `estimated_diameter` JSONB → `estimated_diameter_km_min/max`
3. Deduplicate against `silver.neo` (left anti-join on `neo_id`)
4. Run DQ checks: non-null `neo_id`, unique `neo_id`, abs-magnitude range
5. Write new rows to `silver.neo`
6. Build `silver.neo_close_approach` facts:
   - Extract `relative_velocity` and `miss_distance` from JSONB
   - Join with `silver.neo` for `neo_sk` surrogate key
   - Deduplicate on `(neo_id, close_approach_date_full, orbiting_body)`
   - Write to `silver.neo_close_approach`

### CelesTrak Job (`bronze_to_silver_celestrak.py`)

1. Read `bronze.celestrak_satcat_raw` (306K+ rows)
2. Extract all fields from `parsed_record` JSONB (NORAD ID, orbital params, dates)
3. Deduplicate satellite dimension against `silver.satcat_satellite`
4. Run DQ checks: non-null `norad_cat_id`, unique `norad_cat_id`, non-null `object_name`
5. Write new satellites to `silver.satcat_satellite`
6. Build `silver.satcat_orbit_snapshot` facts (period, inclination, apogee, perigee)
7. Deduplicate on `(norad_cat_id, snapshot_date)` before writing

---

## dbt Transformations (Silver → Gold)

The dbt project (`dbt/space_objects/`) uses:
- **Ephemeral** silver models (inline CTEs, no physical objects created)
- **Table** materialization for all gold models
- `generate_schema_name` macro to route models to the correct schema

### Gold Models

| Model | Source tables | Description |
|---|---|---|
| `neo_daily_activity` | `silver.neo_close_approach`, `silver.neo` | Daily close-approach counts + hazard totals |
| `neo_hazard_summary` | `silver.neo_close_approach`, `silver.neo` | Per-NEO: approaches, closest km, hazard flag |
| `ai_neo_features` | `silver.neo_close_approach`, `silver.neo` | ML features: magnitude, diameter, velocity, distance |
| `ai_satcat_features` | `silver.satcat_orbit_snapshot`, `silver.satcat_satellite` | ML features: period, inclination, apogee, perigee, orbit type |
| `satcat_orbit_summary` | `silver.satcat_satellite`, `silver.satcat_orbit_snapshot` | Orbital characteristics roll-up per satellite |

---

## Pipeline Observability

Every Spark job execution writes to `meta.pipeline_run`:

```sql
SELECT pipeline_name, status, start_time, end_time,
       end_time - start_time AS duration
FROM meta.pipeline_run
ORDER BY start_time DESC
LIMIT 20;
```

DQ check results are in `meta.data_quality_run` (FK to `pipeline_run`):

```sql
SELECT check_name, status, total_records, failed_records, details
FROM meta.data_quality_run
ORDER BY created_at DESC;
```
