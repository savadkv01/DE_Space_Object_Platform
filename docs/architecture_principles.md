Single docker-compose.yml for all core services (Kafka, Spark, Airflow, dbt-runner, Postgres, Prometheus, Grafana).
Separate service-specific folders:
infra/kafka/, infra/spark/, infra/airflow/, infra/postgres/, infra/monitoring/.
Use environment variables and .env files for:
API keys (NASA), DB credentials, Kafka bootstrap servers.
Persistent volumes for:
Postgres data, Airflow logs & metadata, Kafka logs, optional Spark history.


Tech Stack is fixed to Kafka + Spark + Airflow + dbt + Postgres, all Dockerized.
Data sources: NASA NEO (primary) and CelesTrak (secondary).
Architecture pattern: Medallion (Bronze/Silver/Gold) with:
Bronze: “as-ingested,” low transformation.
Silver: normalized & cleaned.
Gold: analytics-friendly.
Both batch and streaming paths are first-class citizens.
Postgres as single data warehouse:
Avoids multiple storage systems to keep project focused.
Single-node deployment optimized for clarity, not max performance.