# Local Environment – Space Objects Data Platform

## System Requirements

| Requirement | Minimum |
|---|---|
| Docker | 20.x+ |
| Docker Compose | v2+ |
| CPU | 4 cores |
| RAM | 8 GB (16 GB recommended) |
| Disk | 20 GB free |
| OS | Linux, macOS, Windows (WSL2 backend) |

---

## Network

All services connect via a single Docker bridge network named `space_net`.  
Docker Compose auto-names it: `space_object_platform_space_net`

Internal service DNS (container-to-container):

| Service | Hostname | Port |
|---|---|---|
| PostgreSQL | `postgres` | `5432` |
| Kafka | `kafka` | `9092` |
| Zookeeper | `zookeeper` | `2181` |
| Spark Master | `spark-master` | `7077` |
| Airflow Scheduler | `airflow-scheduler` | — |

**Host-exposed ports:**

| Service | Host | Container |
|---|---|---|
| PostgreSQL | 15432 | 5432 |
| Kafka | 19092 | 9092 |
| Airflow | 8080 | 8080 |
| Spark Master UI | 8081 | 8080 |
| Grafana | 3000 | 3000 |
| Prometheus | 9090 | 9090 |

> Ports 5432 and 9092 are remapped to avoid conflicts with other local services.

---

## Environment Variables

Copy `.env.example` to `.env` before starting:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `NASA_API_KEY` | Yes | NASA NeoWs API key (get free at https://api.nasa.gov/) |
| `POSTGRES_USER` | Yes | DB username (default: `space_user`) |
| `POSTGRES_PASSWORD` | Yes | DB password (default: `space_password`) |
| `POSTGRES_DB` | Yes | Database name (default: `space_warehouse`) |
| `POSTGRES_JDBC_URL` | Auto | Set to `jdbc:postgresql://postgres:5432/space_warehouse` |
| `KAFKA_BOOTSTRAP_SERVERS` | Auto | Set to `kafka:9092` for internal use |
| `KAFKA_CLIENT_ID` | Optional | Kafka producer client ID |

---

## Database Access

**From host machine (PostgreSQL client):**
```bash
psql -h localhost -p 15432 -U space_user -d space_warehouse
```

**From inside containers:**
```bash
docker exec -it space_object_platform-postgres-1 psql -U space_user -d space_warehouse
```

**JDBC URL (Spark jobs):**
```
jdbc:postgresql://postgres:5432/space_warehouse
```

---

## Airflow

- **UI:** http://localhost:8080
- **Credentials:** admin / admin
- **DAG folder:** `airflow/dags/` (volume-mounted)
- **Executor:** LocalExecutor
- **DB:** PostgreSQL (`public` schema)

To trigger a DAG manually:
```bash
docker exec space_object_platform-airflow-scheduler-1 \
  airflow dags trigger neo_batch_dag
```

---

## Spark

- **Image:** `apache/spark:3.5.5-scala2.12-java17-python3-ubuntu`
- **Master UI:** http://localhost:8081
- **SPARK_HOME:** `/opt/spark`
- **Job files:** volume-mounted to `/opt/spark/jobs`
- **JDBC driver:** PostgreSQL 42.7.3 in `/opt/spark/jars/`

Submit a job:
```bash
docker exec space_object_platform-spark-master-1 bash -c "
  export PYTHONPATH=/opt/spark/jobs \
    POSTGRES_HOST=postgres POSTGRES_PORT=5432 \
    POSTGRES_USER=space_user POSTGRES_PASSWORD=space_password \
    POSTGRES_DB=space_warehouse \
    POSTGRES_JDBC_URL='jdbc:postgresql://postgres:5432/space_warehouse' && \
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.host=spark-master \
    /opt/spark/jobs/bronze_to_silver_neo.py"
```

---

## dbt

- **Version:** dbt-core 1.8.2 + dbt-postgres 1.8.2
- **Profile:** `space_objects` (in `/dbt/profiles.yml`)
- **Target schema:** `gold` (for gold models); `silver` (for source tables)
- **Project path:** `/dbt/space_objects` inside airflow container

Run dbt:
```bash
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt run --profiles-dir /dbt --target dev"
```

> **Note:** dbt silver models use `ephemeral` materialization to avoid naming conflicts with Spark-managed silver tables.

---

## Kafka

- **Image:** `confluentinc/cp-kafka:7.6.0`
- **Broker (internal):** `kafka:9092`
- **Broker (host):** `localhost:19092`
- **Topics created by producers:** `nasa_neo_raw`, `celestrak_satcat_raw`

List topics from inside the container:
```bash
docker exec space_object_platform-kafka-1 \
  kafka-topics --bootstrap-server kafka:9092 --list
```

---

## Observability

- **Prometheus:** http://localhost:9090 – scrapes Kafka, Postgres, and node exporters
- **Grafana:** http://localhost:3000 (admin/admin) – dashboards in `monitoring/dashboards/`
- **Pipeline runs:** `SELECT * FROM meta.pipeline_run ORDER BY start_time DESC LIMIT 20;`
- **DQ checks:** `SELECT * FROM meta.data_quality_run ORDER BY created_at DESC;`
