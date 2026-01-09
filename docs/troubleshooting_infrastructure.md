Infrastructure Troubleshooting Guide (Stage 5)
This guide documents the main issues encountered while setting up the local infrastructure stack and how to resolve them.

Covers:

Docker & networking
Postgres
Kafka
Spark
Airflow
dbt
Assumes you’re in the project root (space-objects-platform/) and using docker compose.

1. Quick Infra Health Checklist
Before deep-dive troubleshooting, run:

docker compose up -d --build
docker compose ps
You want to see running status for at least:

postgres
zookeeper
kafka
spark-master
spark-worker
airflow-webserver
airflow-scheduler
Basic smoke tests:

Postgres: from tools container, psql to postgres.
Airflow: http://localhost:8080 opens; basic DAG is visible and runs.
Spark: Spark job runs and Spark UI is reachable (http://localhost:8081).
Kafka: topic create / produce / consume works from inside kafka container.
dbt: dbt debug passes from dbt container.
For any service in Exit state, check logs:

docker compose logs <service-name>
2. Postgres Connectivity & Hostname Issues
2.1 Symptom: could not translate host name "postgres" to address: Try again
Where: Inside a container (or from host by mistake).
Cause:

Command run from the host instead of inside Docker network, or
Container not attached to space_net, or
Service name mismatch.
Fix:

Ensure you are inside a container on the same network:

docker exec -it tools sh
Test DNS resolution:

ping postgres
If ping postgres fails:

Confirm docker-compose.yml has both services on space_net:

services:
  postgres:
    ...
    networks:
      - space_net

  tools:
    ...
    networks:
      - space_net

networks:
  space_net:
Restart:

docker compose down
docker compose up -d --build
Connect to Postgres from inside tools:

apk add --no-cache postgresql-client

psql -h postgres -U space_user -d space_warehouse -c "\dn"
2.2 Symptom: .env is blank / not used
Cause: .env not populated, or not in project root.

Fix:

Copy the sample:

cp .env.example .env
Ensure at least:

POSTGRES_USER=space_user
POSTGRES_PASSWORD=space_password
POSTGRES_DB=space_warehouse
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
Then:

docker compose down
docker compose up -d --build
3. Kafka: Image & Tools
3.1 Symptom: bitnami/kafka:3.6.1: not found
Cause: Using a non-existent image tag for Kafka tools.

Fix:

Use the main Kafka image as tools container or just exec into kafka.
Simplest: remove kafka-tools or define it as:

kafka-tools:
  image: confluentinc/cp-kafka:7.6.0
  container_name: kafka-tools
  command: ["sleep", "3600"]
  networks:
    - space_net
  depends_on:
    - kafka
Or skip kafka-tools and use:

docker exec -it kafka bash
to run CLI.

3.2 Kafka CLI sanity test
Inside kafka (or kafka-tools) container:

# list topics
kafka-topics --bootstrap-server kafka:9092 --list

# create a topic
kafka-topics --bootstrap-server kafka:9092 \
  --create --topic test_topic --partitions 1 --replication-factor 1

# produce messages
kafka-console-producer --broker-list kafka:9092 --topic test_topic
# type some lines, then Ctrl+C

# consume
kafka-console-consumer --bootstrap-server kafka:9092 \
  --topic test_topic --from-beginning --max-messages 2
4. Spark: Image Tags & Web UI Port
4.1 Symptom: bitnami/spark:3.5.0: not found / bitnami/spark:3: not found
Cause: Non-existent Bitnami Spark tags.

Fix:

Use the generic latest tag:

infra/spark/Dockerfile:

FROM bitnami/spark:latest

USER root
RUN install_packages python3 python3-pip && \
    pip3 install --no-cache-dir psycopg2-binary requests

COPY spark-defaults.conf /opt/bitnami/spark/conf/spark-defaults.conf

USER 1001
Rebuild:

docker compose build spark-master spark-worker
4.2 Symptom: Spark job works, but Spark UI not accessible at http://localhost:8081
Cause: Wrong port mapping. Spark master UI listens on 8080 in the container.

Fix:

In docker-compose.yml:

spark-master:
  ...
  ports:
    - "7077:7077"
    - "8081:8080"  # HOST:CONTAINER
Then:

docker compose down
docker compose up -d --build
docker compose ps spark-master
Check PORTS shows 0.0.0.0:8081->8080/tcp.

Now open http://localhost:8081.

4.3 Spark ↔ Postgres connectivity test
Create spark_jobs/common/test_spark_connectivity.py and run via:

docker exec -it spark-master bash

spark-submit \
  --master spark://spark-master:7077 \
  --packages org.postgresql:postgresql:42.7.3 \
  /opt/bitnami/spark/jobs/common/test_spark_connectivity.py
Should show a small DataFrame and write/read to meta.spark_connectivity_test.

5. Airflow: EntryPoint, DB Init, Fernet Key, Users, DAGs
5.1 Symptom: /entrypoint.sh: no such file or directory
Cause: entrypoint.sh referenced in ENTRYPOINT or docker-compose.yml but not copied into the image.

Simple fix: Use default Airflow entrypoint; no custom script.

infra/airflow/Dockerfile:

FROM apache/airflow:2.8.3-python3.11

USER airflow

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
docker-compose.yml Airflow services (no entrypoint:):

airflow-webserver:
  build:
    context: ./infra/airflow
  container_name: airflow-webserver
  env_file:
    - .env
    - ./infra/airflow/airflow.env
  command: ["webserver"]
  ...

airflow-scheduler:
  build:
    context: ./infra/airflow
  container_name: airflow-scheduler
  env_file:
    - .env
    - ./infra/airflow/airflow.env
  command: ["scheduler"]
  ...
Rebuild and restart.

5.2 Symptom: ERROR: You need to initialize the database. Please run airflow db init
Cause: Airflow metadata DB not initialized.

Fix (one-off run):

docker compose run --rm airflow-webserver airflow db init
Make sure DB URL in infra/airflow/airflow.env is correct:

AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://space_user:space_password@postgres:5432/space_warehouse
5.3 Symptom: Fernet key must be 32 url-safe base64-encoded bytes
Cause: AIRFLOW__CORE__FERNET_KEY is invalid.

Fix:

Generate key on host:

python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Set in infra/airflow/airflow.env:

AIRFLOW__CORE__FERNET_KEY=<generated_key_here>
Then:

docker compose down
docker compose up -d postgres
docker compose run --rm airflow-webserver airflow db init
5.4 Symptom: airflow users create ... command error: arguments required
Cause: On Windows shells, line continuations (\) not handled; only part of the command passed.

Fix: Use a single-line command:

docker compose run --rm airflow-webserver airflow users create \
  --username admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com \
  --password admin
If shell doesn’t like \, run as:
docker compose run --rm airflow-webserver airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@example.com --password admin

5.5 Symptom: Airflow webserver exits immediately printing CLI help (airflow command error: GROUP_OR_COMMAND required)
Cause: Container runs airflow with no subcommand (entrypoint/command mismatch).

Fix: Ensure:

No custom ENTRYPOINT forcing airflow alone.
command: ["webserver"] and command: ["scheduler"] set in compose as above.
5.6 Symptom: DAG file not visible in UI
Checklist:

File mounted: Inside airflow-webserver:

docker exec -it airflow-webserver bash
ls -R /opt/airflow/dags
Ensure hello_world_dag.py is under /opt/airflow/dags.

Syntax OK:

python -m py_compile /opt/airflow/dags/hello_world_dag.py
Minimal DAG example (host: airflow/dags/hello_world_dag.py):

from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="hello_world_dag",
    description="Simple hello world DAG",
    start_date=datetime(2025, 1, 1),
    schedule_interval="@once",
    catchup=False,
    tags=["test"],
) as dag:
    hello = BashOperator(
        task_id="say_hello",
        bash_command="echo 'Hello from Airflow!'",
    )
DAG discovery CLI:

airflow dags list | grep hello_world_dag
UI import errors: Check Browse → DAGs → Import Errors for any tracebacks.

6. dbt: Container, Profiles, Project & Versions
6.1 Symptom: Error response from daemon: container <id> is not running when using docker exec -it dbt bash
Cause: dbt service not running; dbt is designed to be used via docker compose run.

Fix: Use one-off container:

docker compose run --rm dbt bash
This starts a temporary dbt container, then removes it when you exit.

If you want it long-running (not necessary):

docker compose up -d dbt
docker exec -it dbt bash
6.2 Symptom: profiles.yml file [ERROR not found], dbt_project.yml file [ERROR invalid]
Cause: dbt can’t find a valid profiles.yml or dbt_project.yml.

Fix:

docker-compose.yml dbt service:

dbt:
  build:
    context: ./infra/dbt
  container_name: dbt
  env_file:
    - .env
  environment:
    - DBT_PROFILES_DIR=/dbt
  working_dir: /dbt/space_objects
  volumes:
    - ./dbt:/dbt
  networks:
    - space_net
  depends_on:
    - postgres
Host: dbt/profiles.yml:

space_objects:
  target: dev
  outputs:
    dev:
      type: postgres
      host: postgres
      user: space_user
      password: space_password
      port: 5432
      dbname: space_warehouse
      schema: silver
      threads: 4
Host: dbt/space_objects/dbt_project.yml:

name: "space_objects"
version: "1.0.0"
config-version: 2

profile: "space_objects"

model-paths: ["models"]
analysis-paths: ["analysis"]
test-paths: ["tests"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
snapshot-paths: ["snapshots"]

models:
  space_objects:
    +schema: "silver"
    bronze:
      +schema: "bronze"
    silver:
      +schema: "silver"
    gold:
      +schema: "gold"
Then inside dbt container:

dbt debug
6.3 Symptom: Pip conflicts when pinning dbt versions (protobuf / dbt-adapters issues)
Cause: Over-constraining dbt-core / dbt-postgres versions in Dockerfile (e.g., dbt-postgres==1.11.2 not existing, or manual dbt-core==1.10.0 conflicting with new dbt-adapters).

Fix:

Let dbt-postgres pull in compatible versions:

infra/dbt/Dockerfile:

FROM python:3.11-slim

WORKDIR /dbt

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libpq-dev build-essential git && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir dbt-postgres
Then:

docker compose build dbt
docker compose run --rm dbt bash
dbt --version
cd /dbt/space_objects
dbt debug
Should show all checks passed.

7. General Patterns & Tips
Always restart stack cleanly after major config changes:

docker compose down
docker compose up -d --build
To debug a single service:

docker compose up <service>      # foreground logs
docker compose logs <service>    # last logs
Keep .env and airflow.env minimal and consistent; DB host must match the Postgres service name (postgres).

Use docker compose run --rm <service> ... for one-off commands (Airflow db init, airflow users create, dbt debug).