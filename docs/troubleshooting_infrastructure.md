# Infrastructure Troubleshooting Guide (Stage 5)

This guide documents the main issues encountered while setting up the **local infrastructure stack** and how to resolve them.

## Scope

Covers troubleshooting for:

- Docker & networking
- Postgres
- Kafka
- Spark
- Airflow
- dbt

**Assumptions:**
- You are in the project root: `space-objects-platform/`
- You are using `docker compose`

---

## 1. Quick Infra Health Checklist

Before deep-dive troubleshooting, run:

```bash
docker compose up -d --build
docker compose ps
You should see running status for at least:

postgres

zookeeper

kafka

spark-master

spark-worker

airflow-webserver

airflow-scheduler

Basic Smoke Tests
Postgres: From tools container, connect via psql

Airflow: http://localhost:8080 opens; basic DAG is visible and runs

Spark: Spark job runs; Spark UI reachable at http://localhost:8081

Kafka: Topic create / produce / consume works inside Kafka container

dbt: dbt debug passes inside dbt container

For any service in Exit state:

bash
Copy code
docker compose logs <service-name>
2. Postgres Connectivity & Hostname Issues
2.1 Symptom
could not translate host name "postgres" to address: Try again

Where: Inside a container (or command run from host by mistake)

Cause:

Command executed on host instead of Docker network

Container not attached to space_net

Service name mismatch

Fix:

Ensure you are inside a container on the same network:

bash
Copy code
docker exec -it tools sh
Test DNS resolution:

bash
Copy code
ping postgres
If ping postgres fails, confirm docker-compose.yml:

yaml
Copy code
services:
  postgres:
    networks:
      - space_net

  tools:
    networks:
      - space_net

networks:
  space_net:
Restart stack:

bash
Copy code
docker compose down
docker compose up -d --build
Connect to Postgres:

bash
Copy code
apk add --no-cache postgresql-client

psql -h postgres -U space_user -d space_warehouse -c "\dn"
2.2 Symptom
.env is blank / not used

Cause:

.env not populated

.env not located in project root

Fix:

bash
Copy code
cp .env.example .env
Ensure at least:

env
Copy code
POSTGRES_USER=space_user
POSTGRES_PASSWORD=space_password
POSTGRES_DB=space_warehouse
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
Restart:

bash
Copy code
docker compose down
docker compose up -d --build
3. Kafka: Image & Tools
3.1 Symptom
bitnami/kafka:3.6.1: not found

Cause:
Non-existent Kafka image tag.

Fix:

Use main Kafka image or exec directly into Kafka.

Optional tools container:

yaml
Copy code
kafka-tools:
  image: confluentinc/cp-kafka:7.6.0
  container_name: kafka-tools
  command: ["sleep", "3600"]
  networks:
    - space_net
  depends_on:
    - kafka
Or simply:

bash
Copy code
docker exec -it kafka bash
3.2 Kafka CLI Sanity Test
Inside Kafka container:

bash
Copy code
# list topics
kafka-topics --bootstrap-server kafka:9092 --list

# create topic
kafka-topics --bootstrap-server kafka:9092 \
  --create --topic test_topic --partitions 1 --replication-factor 1

# produce messages
kafka-console-producer --broker-list kafka:9092 --topic test_topic

# consume messages
kafka-console-consumer --bootstrap-server kafka:9092 \
  --topic test_topic --from-beginning --max-messages 2
4. Spark: Image Tags & Web UI
4.1 Symptom
bitnami/spark:3.5.0 or bitnami/spark:3 not found

Cause:
Invalid Spark image tags.

Fix:

infra/spark/Dockerfile:

dockerfile
Copy code
FROM bitnami/spark:latest

USER root
RUN install_packages python3 python3-pip && \
    pip3 install --no-cache-dir psycopg2-binary requests

COPY spark-defaults.conf /opt/bitnami/spark/conf/spark-defaults.conf

USER 1001
Rebuild:

bash
Copy code
docker compose build spark-master spark-worker
4.2 Symptom
Spark UI not accessible at http://localhost:8081

Cause:
Wrong port mapping.

Fix:

yaml
Copy code
spark-master:
  ports:
    - "7077:7077"
    - "8081:8080"
Restart:

bash
Copy code
docker compose down
docker compose up -d --build
Open: http://localhost:8081

4.3 Spark ↔ Postgres Connectivity Test
Run from Spark master:

bash
Copy code
docker exec -it spark-master bash

spark-submit \
  --master spark://spark-master:7077 \
  --packages org.postgresql:postgresql:42.7.3 \
  /opt/bitnami/spark/jobs/common/test_spark_connectivity.py
Expected: DataFrame read/write to meta.spark_connectivity_test.

5. Airflow Troubleshooting
5.1 Symptom
/entrypoint.sh: no such file or directory

Cause:
Custom entrypoint referenced but not copied.

Fix:
Use default Airflow entrypoint.

infra/airflow/Dockerfile:

dockerfile
Copy code
FROM apache/airflow:2.8.3-python3.11

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
Compose services must specify commands:

yaml
Copy code
command: ["webserver"]
command: ["scheduler"]
5.2 Symptom
You need to initialize the database

Fix:

bash
Copy code
docker compose run --rm airflow-webserver airflow db init
Verify DB URL in airflow.env.

5.3 Symptom
Invalid Fernet key

Fix:

bash
Copy code
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Set AIRFLOW__CORE__FERNET_KEY and re-init DB.

5.4 Symptom
airflow users create fails on Windows

Fix:
Use a single-line command:

bash
Copy code
docker compose run --rm airflow-webserver airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@example.com --password admin
5.5 Symptom
Webserver exits printing CLI help

Fix:

No custom ENTRYPOINT

Explicit command: ["webserver"] / ["scheduler"]

5.6 Symptom
DAG not visible in UI

Checklist:

DAG exists under /opt/airflow/dags

Syntax valid (py_compile)

Check UI → Import Errors

Verify with:

bash
Copy code
airflow dags list
6. dbt Troubleshooting
6.1 Symptom
container dbt is not running

Fix:

bash
Copy code
docker compose run --rm dbt bash
6.2 Symptom
profiles.yml or dbt_project.yml not found

Fix:

Set DBT_PROFILES_DIR

Mount /dbt

Verify profiles and project config

Run:

bash
Copy code
dbt debug
6.3 Symptom
Pip conflicts with dbt versions

Cause:
Over-pinning dbt versions.

Fix:

infra/dbt/Dockerfile:

dockerfile
Copy code
FROM python:3.11-slim
WORKDIR /dbt

RUN apt-get update && \
    apt-get install -y libpq-dev build-essential git && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir dbt-postgres
Rebuild and verify:

bash
Copy code
dbt --version
dbt debug
7. General Patterns & Tips
Always restart cleanly after config changes:

bash
Copy code
docker compose down
docker compose up -d --build
Debug single service:

bash
Copy code
docker compose up <service>
docker compose logs <service>
Use docker compose run --rm for one-off commands

Keep .env and airflow.env minimal and consistent

DB host must match Postgres service name: postgres