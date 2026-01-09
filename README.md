# Space Objects Data Platform

An on-prem, Dockerized data platform for ingesting and analyzing **Near-Earth Objects (NEOs)** from the NASA NEO API and **satellite catalog data** from CelesTrak.

The platform demonstrates:

- Batch and streaming (later) ingestion
- Medallion architecture (Bronze / Silver / Gold)
- Apache Spark + Kafka + Airflow + dbt + Postgres
- Logging, monitoring, observability
- Production-style Python code and infrastructure

---

## 1. Project Overview

**Goal:** Build a realistic “Space Object Situational Awareness Platform” that allows analysts and engineers to:

- Monitor near-Earth objects and their close approaches to Earth.
- Analyze satellite catalog and orbital characteristics over time.

**Primary sources:**

- **NASA NEO API (NeoWs)** – Near-Earth Objects (asteroids) and their close-approach events.
- **CelesTrak SATCAT** – Satellite catalog (CSV) and TLEs (later) for orbital data.

**Key personas:**

- Space risk analysts – hazardous NEO dashboards.
- Data scientists – clean Silver data for modeling.
- Data engineers – robust, observable pipelines.

---

## 2. Architecture Summary

All components run in Docker (single node):

- **Storage / Warehouse**
  - PostgreSQL (`space_warehouse` DB)
  - Schemas: `bronze`, `silver`, `gold`, `meta`, `dq`

- **Processing**
  - Apache Spark (master + worker)
  - Python batch ingestion jobs
  - Spark (later) for Bronze → Silver

- **Messaging**
  - Apache Kafka + Zookeeper
  - (Streaming ingestion will be added later)

- **Orchestration**
  - Apache Airflow (webserver + scheduler)
  - Currently used for validation and will orchestrate ingestion / transforms later

- **Transformations**
  - dbt (Postgres target)
  - Used for Silver → Gold modeling (later stages)

- **Observability**
  - Prometheus (metrics)
  - Grafana (dashboards)
  - Structured logging + Postgres `meta` tables for run metadata

- **Batch ingestion (implemented)**
  - `nasa-neo-batch` → `bronze.nasa_neo_event_raw`
  - `celestrak-batch` → `bronze.celestrak_satcat_raw`

---

## 3. Tech Stack

- **Core**
  - Python 3.11
  - PostgreSQL 15
  - Apache Spark (bitnami/spark)
  - Apache Kafka (confluentinc/cp-kafka) + Zookeeper
  - Apache Airflow 2.8.x
  - dbt (dbt-postgres)
  - Prometheus + Grafana

- **Containerization**
  - Docker
  - Docker Compose

---

## 4. Repository Structure

```bash
space-objects-platform/
  docker-compose.yml
  .env.example
  .gitignore
  README.md

  infra/
    postgres/
      Dockerfile
      init.sql
    kafka/
      docker-compose.env
    spark/
      Dockerfile
      spark-defaults.conf
    airflow/
      Dockerfile
      requirements.txt
      airflow.env
    dbt/
      Dockerfile
    ingestion/
      Dockerfile
      requirements.txt
    monitoring/
      prometheus.yml
      grafana/

  services/
    common/
      __init__.py
      config_loader.py
      db_client.py
      logging_utils.py
    ingestion/
      base_ingestion.py
      nasa_neo/
        __init__.py
        neo_client.py
        neo_batch_ingestor.py
      celestrak/
        __init__.py
        celestrak_client.py
        celestrak_batch_ingestor.py

  spark_jobs/
    common/
      __init__.py
      spark_job_base.py
      test_spark_connectivity.py   # example connectivity test

  airflow/
    dags/
      hello_world_dag.py
    logs/
    plugins/

  dbt/
    profiles.yml
    space_objects/
      dbt_project.yml
      models/
        bronze/
        silver/
        gold/

  monitoring/
    dashboards/

  docs/
    scope.md
    architecture.md
    environment.md
    source_data.md
    data_model.md
    observability.md
    troubleshooting_infrastructure.md


## 5. Prerequisites

- Docker (20.x+) and Docker Compose (v2+)
- Recommended resources:
    - CPU: 4+ cores
    - RAM: 8–16 GB
    - Disk: ≥ 20 GB free
- Internet connectivity from containers (for NASA & CelesTrak APIs)
On Windows, using WSL2 is recommended for a smoother Docker experience.
