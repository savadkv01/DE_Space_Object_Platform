# Project Architecture & Design

## Container & Infrastructure Setup

- Single `docker-compose.yml` for all core services:
  - Kafka
  - Spark
  - Airflow
  - dbt-runner
  - Postgres
  - Prometheus
  - Grafana

- Separate service-specific folders:
  - `infra/kafka/`
  - `infra/spark/`
  - `infra/airflow/`
  - `infra/postgres/`
  - `infra/monitoring/`

### Environment Configuration

- Environment variables and `.env` files are used for:
  - API keys (NASA)
  - Database credentials
  - Kafka bootstrap servers

> ⚠️ `.env` files must not be committed to GitHub.

### Persistent Volumes

Persistent volumes are configured for:
- Postgres data
- Airflow logs and metadata
- Kafka logs
- Optional Spark history

---

## Technology Stack

- **Tech Stack (Fixed):**
  - Kafka
  - Spark
  - Airflow
  - dbt
  - Postgres  
  *(All services are Dockerized)*

- **Data Sources:**
  - NASA NEO (Primary)
  - CelesTrak (Secondary)

---

## Architecture Pattern

- **Architecture Pattern:** Medallion Architecture (Bronze / Silver / Gold)

### Medallion Layers

- **Bronze**
  - As-ingested data
  - Minimal or no transformation

- **Silver**
  - Normalized and cleaned data

- **Gold**
  - Analytics-ready, business-friendly datasets

- Both **batch** and **streaming** pipelines are treated as first-class citizens.

---

## Data Warehouse Strategy

- **Postgres as the single data warehouse**
  - Avoids multiple storage systems
  - Keeps the project focused and easier to understand
  - Single-node deployment optimized for clarity, not maximum performance

---

## Bronze Ingestion Status

### Confirmed Bronze Tables

The following Bronze tables are populated via **batch ingestion**:

- `bronze.nasa_neo_event_raw`
- `bronze.celestrak_satcat_raw`

### Notes

- JSON fields in these tables (e.g., `estimated_diameter`, `relative_velocity`) are stored as `jsonb`.
- These fields will be normalized into **Silver** using Spark in later stages.
