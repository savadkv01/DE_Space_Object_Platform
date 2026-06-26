# Command Reference – Space Objects Data Platform

All commands run from the project root unless noted. On Windows, use PowerShell.

---

## 1. Docker Compose Lifecycle

```bash
# Start full stack (builds on first run)
docker compose up -d --build

# Start with synthetic data services
docker compose --profile synthetic up -d --build

# Stop all services
docker compose down

# Stop and remove all volumes (wipes DB, checkpoints)
docker compose down -v

# View service status
docker compose ps

# Tail logs for a service
docker compose logs -f airflow-webserver
docker compose logs -f kafka
docker compose logs -f spark-master
```

---

## 2. Container Access

```bash
# PostgreSQL shell
docker exec -it space_object_platform-postgres-1 psql -U space_user -d space_warehouse

# Airflow scheduler shell
docker exec -it space_object_platform-airflow-scheduler-1 bash

# Spark master shell
docker exec -it space_object_platform-spark-master-1 bash

# Kafka shell
docker exec -it space_object_platform-kafka-1 bash
```

---

## 3. Batch Ingestion (Manual)

```bash
# NASA NEO batch (from airflow-scheduler)
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /opt/airflow && python -c \"
import sys; sys.path.insert(0,'/opt/airflow/services')
from ingestion.nasa_neo.neo_batch_ingestor import NasaNeoBatchIngestionJob
NasaNeoBatchIngestionJob().execute()
\""

# CelesTrak batch (from airflow-scheduler)
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /opt/airflow && python -c \"
import sys; sys.path.insert(0,'/opt/airflow/services')
from ingestion.celestrak.celestrak_batch_ingestor import CelesTrakSatcatBatchIngestionJob
CelesTrakSatcatBatchIngestionJob(group='active').execute()
\""
```

---

## 4. Spark Jobs (Manual)

```bash
# Helper env for Spark jobs
SPARK_ENV="export PYTHONPATH=/opt/spark/jobs \
  POSTGRES_HOST=postgres POSTGRES_PORT=5432 \
  POSTGRES_USER=space_user POSTGRES_PASSWORD=space_password \
  POSTGRES_DB=space_warehouse \
  POSTGRES_JDBC_URL='jdbc:postgresql://postgres:5432/space_warehouse'"

SPARK_SUBMIT="/opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=spark-master"

# NEO bronze → silver
docker exec space_object_platform-spark-master-1 bash -c \
  "$SPARK_ENV && $SPARK_SUBMIT /opt/spark/jobs/bronze_to_silver_neo.py"

# CelesTrak bronze → silver
docker exec space_object_platform-spark-master-1 bash -c \
  "$SPARK_ENV && $SPARK_SUBMIT /opt/spark/jobs/bronze_to_silver_celestrak.py"
```

---

## 5. dbt

```bash
# Run all models
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt run --profiles-dir /dbt --target dev"

# Run only gold models
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt run --select gold.* --profiles-dir /dbt --target dev"

# Run tests
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt test --profiles-dir /dbt --target dev"

# Check dbt version / connection
docker exec space_object_platform-airflow-scheduler-1 bash -c "
  cd /dbt/space_objects
  DBT_LOG_PATH=/tmp/dbt_logs dbt debug --profiles-dir /dbt --target dev"
```

---

## 6. Airflow DAGs

```bash
# List DAGs
docker exec space_object_platform-airflow-scheduler-1 airflow dags list

# Trigger DAG manually
docker exec space_object_platform-airflow-scheduler-1 \
  airflow dags trigger neo_batch_dag

# Check DAG state
docker exec space_object_platform-airflow-scheduler-1 \
  airflow dags state neo_batch_dag $(date +%Y-%m-%dT%H:%M:%S+00:00)
```

---

## 7. Kafka

```bash
# List topics
docker exec space_object_platform-kafka-1 \
  kafka-topics --bootstrap-server kafka:9092 --list

# Create topic manually
docker exec space_object_platform-kafka-1 \
  kafka-topics --bootstrap-server kafka:9092 --create \
  --topic nasa_neo_raw --partitions 1 --replication-factor 1

# Consume messages (latest)
docker exec space_object_platform-kafka-1 \
  kafka-console-consumer --bootstrap-server kafka:9092 \
  --topic nasa_neo_raw --from-beginning --max-messages 5
```

---

## 8. Postgres Queries

```sql
-- All pipeline runs
SELECT pipeline_name, status, start_time, end_time - start_time AS duration
FROM meta.pipeline_run ORDER BY start_time DESC LIMIT 20;

-- DQ check results
SELECT check_name, status, total_records, failed_records, details
FROM meta.data_quality_run ORDER BY created_at DESC LIMIT 20;

-- Row counts across all layers
SELECT 'bronze.nasa_neo_event_raw', count(*) FROM bronze.nasa_neo_event_raw
UNION ALL SELECT 'bronze.celestrak_satcat_raw', count(*) FROM bronze.celestrak_satcat_raw
UNION ALL SELECT 'silver.neo', count(*) FROM silver.neo
UNION ALL SELECT 'silver.neo_close_approach', count(*) FROM silver.neo_close_approach
UNION ALL SELECT 'silver.satcat_satellite', count(*) FROM silver.satcat_satellite
UNION ALL SELECT 'silver.satcat_orbit_snapshot', count(*) FROM silver.satcat_orbit_snapshot
UNION ALL SELECT 'gold.neo_daily_activity', count(*) FROM gold.neo_daily_activity
UNION ALL SELECT 'gold.ai_neo_features', count(*) FROM gold.ai_neo_features;
```

---

## 9. Synthetic Data

```bash
# One-off batch seed (default: 200 NEO, 300 SATCAT)
docker compose --profile synthetic run --rm synthetic-seeder

# Custom counts
docker run --rm \
  --network space_object_platform_space_net \
  -e POSTGRES_HOST=postgres -e POSTGRES_PORT=5432 \
  -e POSTGRES_USER=space_user -e POSTGRES_PASSWORD=space_password \
  -e POSTGRES_DB=space_warehouse \
  space-objects-ingestion \
  python -m services.synthetic.batch_seeder --neo 50 --satcat 100

# Continuous synthetic stream
docker compose --profile synthetic up -d synthetic-stream
```

---

## 10. Reset / Rebuild

```bash
# Rebuild all images without cache
docker compose build --no-cache

# Reset silver layer (drop + re-init via init.sql)
docker exec -i space_object_platform-postgres-1 \
  psql -U space_user -d space_warehouse -c "
    DROP TABLE IF EXISTS silver.neo_close_approach CASCADE;
    DROP TABLE IF EXISTS silver.neo CASCADE;
    DROP TABLE IF EXISTS silver.satcat_orbit_snapshot CASCADE;
    DROP TABLE IF EXISTS silver.satcat_satellite CASCADE;"
docker exec -i space_object_platform-postgres-1 \
  psql -U space_user -d space_warehouse \
  -f /docker-entrypoint-initdb.d/init.sql

# Full reset (removes all data)
docker compose down -v
docker compose up -d --build
```
