Space Object Situational Awareness Platform

Build an on-prem, Dockerized data platform that ingests and processes near-Earth objects (NEOs) from the NASA NEO API and satellite catalog data from CelesTrak, providing analysts and engineers with curated views of:

Potentially hazardous asteroids approaching Earth, and
Satellite orbits and catalog changes over time.
This is positioned as a realistic internal platform for:

Space operations / risk teams: watching potentially hazardous objects.
Data science teams: modeling orbital dynamics and hazard probabilities.
Data analytics / BI teams: building dashboards on NEO & satellite trends.
Platform / data engineering: showcasing a solid, production-minded data platform.


Core Objectives
Ingest NASA NEO & CelesTrak satellite data via:

Batch (historical + periodic refresh)
Streaming (near-real-time simulation via Kafka).
Model data in a Medallion architecture:

Bronze: raw NEO and satellite data (as close to source as possible).
Silver: cleaned, normalized entities (NEOs, close-approach events, satellites, orbit snapshots).
Gold: business-friendly tables for reporting and analysis.
Orchestrate end-to-end pipelines with Airflow:

Batch DAGs (daily NEO, hourly CelesTrak).
Streaming job supervision.
Enable analytics on:

NEO hazard and close-approach statistics.
Satellite catalog changes and orbit distributions.
Demonstrate production practices:

Observability (logs, metrics, structured monitoring).
Configuration management, error handling, idempotency.
Clear documentation and diagrams.
Example Business / Analytical Questions (Gold layer)
NEOs

How many NEOs approach Earth within X lunar distances per day/week?
Which upcoming NEOs are flagged as potentially hazardous by NASA?
Distribution of minimum approach distances and velocities over time.
Trends of discovered NEOs per month.
Satellites

How many active satellites are in a given orbital regime (LEO/MEO/GEO)?
How frequently do TLE parameters change for specific satellites?
Which satellites operated by a given country/operator are in certain inclination ranges?



Scope, Constraints & Assumptions
Hard Constraints
No cloud services.
Everything is local, Docker-only.

Mandatory technologies in Docker:

Apache Spark (PySpark)
Apache Kafka (+ Zookeeper or Kraft)
Apache Airflow
dbt
PostgreSQL (metadata + warehouse)
Optional: Prometheus & Grafana
Data sources

Primary: NASA NEO API (near-Earth object feed & lookup).
Secondary: CelesTrak catalog / TLE data (CSV/TXT feeds).
Assumptions
Single-node / laptop-scale environment:

~16GB RAM recommended; can be tuned down but with trade-offs.
Data Volume (rough expectation; precise will be in Stage 3):

NASA NEO: Hundreds of objects per day; manageable for local Spark.
CelesTrak: Few tens of thousands of satellites/TLE records; also manageable.
Network access is available for:

NASA & CelesTrak APIs from inside Docker containers.
Out-of-Scope (explicitly)
Real mission-critical alerting (e.g., notifying real operations centers).
Highly optimized multi-node cluster tuning.
Complex access control / enterprise-grade security (we’ll do “good practice” basics).