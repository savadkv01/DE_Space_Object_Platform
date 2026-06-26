# Architecture Diagram – Space Objects Data Platform

## System Architecture

```mermaid
flowchart TD
    %% External Sources
    subgraph SOURCES["External Sources"]
        NASA["NASA NEO API\n(NeoWs REST)"]
        CELES["CelesTrak SATCAT API\n(CSV endpoint)"]
    end

    %% Ingestion Layer
    subgraph INGEST["Ingestion Services (Python 3.11)"]
        NEO_BATCH["neo_batch_ingestor\n(retry + backoff)"]
        NEO_STREAM["neo_stream_producer\n(Kafka)"]
        SAT_BATCH["celestrak_batch_ingestor\n(idempotent)"]
        SAT_STREAM["celestrak_stream_producer\n(Kafka)"]
        SYNTH["synthetic/batch_seeder\n(test data)"]
    end

    %% Messaging
    subgraph KAFKA["Apache Kafka (cp-kafka 7.6)"]
        K1["Topic: nasa_neo_raw"]
        K2["Topic: celestrak_satcat_raw"]
    end

    %% Bronze
    subgraph BRONZE["Bronze Layer (PostgreSQL)"]
        B1["bronze.nasa_neo_event_raw"]
        B2["bronze.nasa_neo_feed_raw"]
        B3["bronze.celestrak_satcat_raw"]
        B4["bronze.celestrak_tle_raw"]
    end

    %% Streaming consumers
    subgraph STREAMING["Spark Structured Streaming"]
        S1["neo_stream_to_bronze.py"]
        S2["celestrak_stream_to_bronze.py"]
    end

    %% Spark Batch
    subgraph SPARK_BATCH["Apache Spark 3.5.5 (Batch Jobs)"]
        SP1["bronze_to_silver_neo.py\n(DQ checks + surrogate keys)"]
        SP2["bronze_to_silver_celestrak.py\n(JSONB extraction)"]
    end

    %% Silver
    subgraph SILVER["Silver Layer (PostgreSQL)"]
        SV1["silver.neo\n(dimension, neo_sk)"]
        SV2["silver.neo_close_approach\n(facts)"]
        SV3["silver.satcat_satellite\n(dimension, satellite_sk)"]
        SV4["silver.satcat_orbit_snapshot\n(facts)"]
    end

    %% dbt
    subgraph DBT["dbt 1.8.2 (Gold Models)"]
        D1["neo_daily_activity"]
        D2["neo_hazard_summary"]
        D3["ai_neo_features"]
        D4["ai_satcat_features"]
        D5["satcat_orbit_summary"]
    end

    %% Gold
    subgraph GOLD["Gold Layer (PostgreSQL)"]
        G1["gold.neo_daily_activity"]
        G2["gold.neo_hazard_summary"]
        G3["gold.ai_neo_features"]
        G4["gold.ai_satcat_features"]
        G5["gold.satcat_orbit_summary"]
    end

    %% Meta / DQ
    subgraph META["Meta Layer (PostgreSQL)"]
        M1["meta.pipeline_run"]
        M2["meta.data_quality_run"]
    end

    %% Orchestration
    subgraph AIRFLOW["Apache Airflow 2.8.3"]
        A1["neo_batch_dag @daily"]
        A2["celestrak_batch_dag @daily"]
        A3["bronze_to_silver_dag @daily"]
        A4["dbt_gold_dag @daily"]
        A5["streaming_supervision_dag */10 * * * *"]
    end

    %% Observability
    subgraph OBS["Observability"]
        PROM["Prometheus\n(kafka, postgres, node exporters)"]
        GRAF["Grafana\n(dashboards)"]
    end

    %% Data flow edges
    NASA --> NEO_BATCH --> B1
    NASA --> NEO_BATCH --> B2
    NASA --> NEO_STREAM --> K1
    CELES --> SAT_BATCH --> B3
    CELES --> SAT_STREAM --> K2
    SYNTH --> B1
    SYNTH --> B3

    K1 --> S1 --> B1
    K2 --> S2 --> B3

    B1 --> SP1 --> SV1
    SP1 --> SV2
    B3 --> SP2 --> SV3
    SP2 --> SV4

    SV1 --> D1 & D2 & D3
    SV2 --> D1 & D2 & D3
    SV3 --> D4 & D5
    SV4 --> D4 & D5

    D1 --> G1
    D2 --> G2
    D3 --> G3
    D4 --> G4
    D5 --> G5

    SP1 -.-> M1
    SP2 -.-> M1
    SP1 -.-> M2
    SP2 -.-> M2

    A1 -.->|triggers| NEO_BATCH
    A2 -.->|triggers| SAT_BATCH
    A3 -.->|spark-submit| SP1
    A3 -.->|spark-submit| SP2
    A4 -.->|dbt run + test| DBT
    A5 -.->|monitors| M1

    PROM --> GRAF
```

---

## Container Topology

```mermaid
graph LR
    subgraph DOCKER["Docker Compose — space_object_platform_space_net"]
        PG[("postgres\n:15432→5432")]
        ZK["zookeeper\n:2181"]
        KA["kafka\n:19092→9092"]
        SM["spark-master\n:8081→8080\n:7077"]
        SW["spark-worker"]
        AW["airflow-webserver\n:8080"]
        AS["airflow-scheduler"]
        PR["prometheus\n:9090"]
        GR["grafana\n:3000"]
        KE["kafka-exporter"]
        PE["postgres-exporter"]
        NB["nasa-neo-batch"]
        CB["celestrak-batch"]
        NS["nasa-neo-stream"]
        CS["celestrak-stream"]
    end

    KA --> ZK
    SM --> KA
    SW --> SM
    AW --> PG
    AS --> PG
    AS --> SM
    NB --> PG
    NB --> KA
    CB --> PG
    CB --> KA
    NS --> KA
    CS --> KA
    KE --> KA
    PE --> PG
    PR --> KE
    PR --> PE
    GR --> PR
```

---

## Medallion Architecture

```mermaid
flowchart LR
    subgraph BRONZE["🥉 Bronze\n(Raw / As-ingested)"]
        direction TB
        B1["nasa_neo_event_raw\n40+ rows per day"]
        B2["celestrak_satcat_raw\n~17K rows per snapshot"]
    end

    subgraph SILVER["🥈 Silver\n(Normalized / Spark-managed)"]
        direction TB
        S1["neo\ndimension"]
        S2["neo_close_approach\nfacts"]
        S3["satcat_satellite\ndimension"]
        S4["satcat_orbit_snapshot\nfacts"]
    end

    subgraph GOLD["🥇 Gold\n(Analytics-ready / dbt-managed)"]
        direction TB
        G1["neo_daily_activity"]
        G2["neo_hazard_summary"]
        G3["ai_neo_features"]
        G4["ai_satcat_features"]
        G5["satcat_orbit_summary"]
    end

    B1 -->|"Spark\nbronze_to_silver_neo"| S1
    B1 --> S2
    B2 -->|"Spark\nbronze_to_silver_celestrak"| S3
    B2 --> S4

    S1 & S2 -->|"dbt\ngold models"| G1 & G2 & G3
    S3 & S4 --> G4 & G5
```

---

## Pipeline Orchestration (DAG Dependencies)

```mermaid
gantt
    title Daily Pipeline Schedule (UTC)
    dateFormat HH:mm
    section Ingestion
    neo_batch_dag           :00:00, 5m
    celestrak_batch_dag     :00:05, 10m
    section Transformation
    bronze_to_silver_dag    :00:20, 15m
    dbt_gold_dag            :00:40, 5m
    section Monitoring
    streaming_supervision   :00:00, 1m
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Warehouse | PostgreSQL 15 | Single storage system; avoids multi-system complexity |
| Spark image | `apache/spark:3.5.5` | Official image; bitnami 3.5.5 does not exist |
| Spark → Postgres | JDBC + `stringtype=unspecified` | Allows varchar → uuid implicit cast |
| pipeline_run insert | psycopg2 at job start | Enables FK from data_quality_run; JDBC can't UPDATE |
| dbt silver models | Ephemeral | Avoids naming collision with Spark-managed tables |
| dbt schema routing | `generate_schema_name` macro | Bypasses dbt's default `{profile_schema}_{model_schema}` prefix |
| Port remapping | 15432, 19092 | Avoids conflicts with other local Postgres/Kafka instances |
| Synthetic data | `services/synthetic/` | Physically realistic; enables offline testing |
| Kafka healthcheck | `kafka-broker-api-versions` | Works inside cp-kafka without separate tools |
