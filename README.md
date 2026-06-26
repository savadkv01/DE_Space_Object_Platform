# Space Objects Data Platform

An on-prem, Dockerized data platform for ingesting and analyzing **Near-Earth Objects (NEOs)** from the NASA NEO API and **satellite catalog data** from CelesTrak.

The platform demonstrates a production-style end-to-end data engineering stack:
- Batch and streaming ingestion via Kafka
- Medallion architecture (Bronze → Silver → Gold) in PostgreSQL
- Apache Spark for transformations, dbt for gold-layer modeling
- Apache Airflow for orchestration
- Prometheus + Grafana for observability
- Synthetic data generation for local testing

---

## 1. Project Overview

**Goal:** Build a realistic "Space Object Situational Awareness Platform" that allows analysts and engineers to:

- Monitor near-Earth objects and their close approaches to Earth.
- Analyze satellite catalog and orbital characteristics over time.

**Primary sources:**
- **NASA NEO API (NeoWs)** – Near-Earth Objects (asteroids) and their close-approach events.
- **CelesTrak SATCAT** – Satellite catalog (CSV) with orbital parameters.

**Key personas:**
- Space risk analysts – hazardous NEO dashboards.
- Data scientists – clean Silver/Gold data for ML modeling.
- Data engineers – robust, observable pipelines.

---

## 2. Architecture Summary

All components run in Docker (single-node). See [docs/architecture_principles.md](docs/architecture_principles.md) and [docs/architecture.md](docs/architecture.md) for the full architecture diagram.

| Component | Technology | Notes |
|---|---|---|
| Warehouse | PostgreSQL 15 (`space_warehouse`) | Schemas: bronze/silver/gold/meta/dq |
| Messaging | Kafka (cp-kafka 7.6) + Zookeeper | Topics: nasa_neo_raw, celestrak_satcat_raw |
| Processing | Apache Spark 3.5.5 | Master + 1 worker; batch bronze→silver |
| Orchestration | Apache Airflow 2.8.3 | 5 DAGs; LocalExecutor |
| Modeling | dbt 1.8.2 | 5 gold tables; ephemeral silver pass-throughs |
| Observability | Prometheus + Grafana | Kafka, Postgres, node exporters |
| Ingestion | Python 3.11 services | Batch + streaming; retry/backoff |

**Host port mappings:**

| Service | Host Port | Container Port |
|---|---|---|
| PostgreSQL | 15432 | 5432 |
| Kafka | 19092 | 9092 |
| Airflow UI | 8080 | 8080 |
| Spark Master UI | 8081 | 8080 |
| Grafana | 3000 | 3000 |
| Prometheus | 9090 | 9090 |

---

## 3. Data Flow

```
NASA NEO API ──► neo-batch-ingestor ─────────────────► bronze.nasa_neo_event_raw
                 neo-stream-producer ──► Kafka topic ──► Spark Streaming ──► bronze

CelesTrak API ──► celestrak-batch ───────────────────► bronze.celestrak_satcat_raw
                  celestrak-stream ──► Kafka topic ──► Spark Streaming ──► bronze

Synthetic ───────► services/synthetic/batch_seeder ──► bronze.* (test data)

bronze.* ────────► Spark (bronze_to_silver_neo.py) ──► silver.neo
                                                        silver.neo_close_approach
                   Spark (bronze_to_silver_celestrak) ► silver.satcat_satellite
                                                        silver.satcat_orbit_snapshot

silver.* ────────► dbt (gold models) ───────────────► gold.neo_daily_activity
                                                       gold.neo_hazard_summary
                                                       gold.ai_neo_features
                                                       gold.ai_satcat_features
                                                       gold.satcat_orbit_summary

meta.pipeline_run + meta.data_quality_run track every job execution and DQ result.
```

---

## 4. Repository Structure

```
space_object_platform/
├── docker-compose.yml          # All service definitions
├── README.md
├── .env.example
│
├── infra/
│   ├── postgres/               # Dockerfile + init.sql (full schema DDL)
│   ├── kafka/                  # kafka.env, config/
│   ├── spark/                  # FROM apache/spark:3.5.5; spark-defaults.conf
│   ├── airflow/                # Dockerfile (Spark client + dbt 1.8.2), airflow.env
│   ├── dbt/                    # Dockerfile
│   ├── ingestion/              # Dockerfile, requirements.txt
│   └── monitoring/             # prometheus.yml, Grafana provisioning
│
├── services/
│   ├── common/                 # config_loader, db_client, kafka_client, logging_utils
│   ├── ingestion/
│   │   ├── nasa_neo/           # neo_client (retry), neo_batch_ingestor, neo_stream_producer
│   │   └── celestrak/          # celestrak_client (retry), batch/stream ingestors
│   └── synthetic/              # generators.py, batch_seeder.py, stream_producer.py
│
├── spark_jobs/
│   ├── common/                 # spark_job_base.py (psycopg2 meta), dq_utils.py
│   ├── bronze_to_silver_neo.py
│   ├── bronze_to_silver_celestrak.py
│   └── streaming/              # neo_stream_to_bronze.py, celestrak_stream_to_bronze.py
│
├── airflow/dags/
│   ├── neo_batch_dag.py
│   ├── celestrak_batch_dag.py
│   ├── bronze_to_silver_dag.py
│   ├── dbt_gold_dag.py
│   └── streaming_supervision_dag.py
│
├── dbt/
│   ├── profiles.yml            # schema: public; generate_schema_name macro routes to gold/silver
│   └── space_objects/
│       ├── dbt_project.yml
│       ├── macros/             # generate_schema_name.sql, til.sql
│       └── models/
│           ├── silver/         # Ephemeral models (no physical objects created)
│           └── gold/           # 5 materialized tables in gold schema
│
├── monitoring/dashboards/
└── docs/
    ├── architecture.md         # Mermaid architecture diagram
    ├── architecture_principles.md
    ├── data_flow.md
    ├── environment.md
    ├── commands.md
    ├── observability.md
    ├── scope.md
    ├── source_nasa_neo.md
    ├── source_celestrak.md
    └── troubleshooting_infrastructure.md
```

---

## 5. Prerequisites

- Docker 20.x+ and Docker Compose v2+
- Resources: 4+ CPU cores, 8–16 GB RAM, ≥ 20 GB disk
- Internet access from containers (NASA & CelesTrak APIs)
- NASA API key from https://api.nasa.gov/ (free)
- On Windows: WSL2 backend recommended

---

## 6. Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Set NASA_API_KEY in .env

# 2. Start the full stack
docker compose up -d --build

# 3. Check health
docker compose ps

# 4. Access UIs
#   Airflow:    http://localhost:8080  (admin / admin)
#   Spark UI:   http://localhost:8081
#   Grafana:    http://localhost:3000  (admin / admin)
#   Prometheus: http://localhost:9090

# 5. Run batch ingestion (or trigger neo_batch_dag / celestrak_batch_dag in Airflow)
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /opt/airflow && python -c \"
import sys; sys.path.insert(0,'/opt/airflow/services')
from ingestion.nasa_neo.neo_batch_ingestor import NasaNeoBatchIngestionJob
NasaNeoBatchIngestionJob().execute()
\""

# 6. Run Spark bronze→silver transformations
docker exec space_object_platform-spark-master-1 bash -c "
  export PYTHONPATH=/opt/spark/jobs \
    POSTGRES_HOST=postgres POSTGRES_PORT=5432 \
    POSTGRES_USER=space_user POSTGRES_PASSWORD=space_password \
    POSTGRES_DB=space_warehouse \
    POSTGRES_JDBC_URL='jdbc:postgresql://postgres:5432/space_warehouse'
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.host=spark-master \
    /opt/spark/jobs/bronze_to_silver_neo.py"

# 7. Run dbt gold models
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt run --profiles-dir /dbt --target dev
  DBT_LOG_PATH=/tmp/dbt_logs dbt test --profiles-dir /dbt --target dev"

# 8. Stop
docker compose down
```

---

## 7. Airflow DAGs

| DAG | Schedule | Description |
|---|---|---|
| `neo_batch_dag` | `@daily` | NASA NEO API → bronze |
| `celestrak_batch_dag` | `@daily` | CelesTrak SATCAT → bronze |
| `bronze_to_silver_dag` | `@daily` | Spark: bronze → silver (NEO then CelesTrak) |
| `dbt_gold_dag` | `@daily` | dbt deps → run silver → run gold → test |
| `streaming_supervision_dag` | `*/10 * * * *` | Monitor streaming pipeline health via meta.pipeline_run |

---

## 8. Data Model

### Bronze (raw ingest, schema-on-read)
| Table | Source | Key columns |
|---|---|---|
| `nasa_neo_feed_raw` | NASA NEO API | raw JSON payload |
| `nasa_neo_event_raw` | Parsed from feed | `neo_id`, `close_approach_date`, `relative_velocity` JSONB, `miss_distance` JSONB |
| `celestrak_satcat_raw` | CelesTrak CSV | `norad_cat_id`, `parsed_record` JSONB, `snapshot_date` |
| `celestrak_tle_raw` | CelesTrak TLE | Reserved for future TLE ingestion |

### Silver (normalized, Spark-managed)
| Table | Description |
|---|---|
| `silver.neo` | NEO dimension; surrogate key `neo_sk`; deduped by `neo_id` |
| `silver.neo_close_approach` | Close-approach facts; FK to `neo_sk`; velocity + distance columns |
| `silver.satcat_satellite` | Satellite dimension; `satellite_sk`; deduped by `norad_cat_id` |
| `silver.satcat_orbit_snapshot` | Orbital snapshot facts; period, inclination, apogee, perigee |

### Gold (analytics-ready, dbt-managed in `gold` schema)
| Table | Description |
|---|---|
| `neo_daily_activity` | Daily approach counts, hazardous flag totals |
| `neo_hazard_summary` | Per-NEO roll-up: total approaches, closest km, hazard flag |
| `ai_neo_features` | ML-ready feature table for NEO hazard classification |
| `ai_satcat_features` | ML-ready feature table for satellite orbital analysis |
| `satcat_orbit_summary` | Satellite orbital characteristics summary |

### Meta
| Table | Description |
|---|---|
| `meta.pipeline_run` | Every job execution: start/end time, status, records processed |
| `meta.data_quality_run` | DQ check results per run (FK to pipeline_run) |

---

## 9. Synthetic Data

For local testing without live API calls:

```bash
# One-off batch seed
docker compose --profile synthetic run --rm synthetic-seeder
# Flags: --neo N --satcat N --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Continuous synthetic stream
docker compose --profile synthetic up synthetic-stream
```

Synthetic data is physically realistic (derived orbital periods, log-normal miss distances, hazard distributions) and flows through the full bronze → silver → gold pipeline.

---

## 10. Known Limitations

- `bronze.celestrak_tle_raw` is reserved but no TLE-to-orbital-elements parser is implemented; the CelesTrak silver job reads from `celestrak_satcat_raw` instead.
- Grafana dashboards are provisioned but panels are not yet configured.
- Streaming jobs require Kafka running and are not automatically triggered by Airflow (supervision only).
- `node-exporter` Prometheus scraping is disabled on Docker Desktop (host network limitation).
