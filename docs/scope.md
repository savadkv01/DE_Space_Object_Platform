# Space Object Situational Awareness Platform

## Overview

This project builds an **on-prem, Dockerized data platform** that ingests and processes:

- **Near-Earth Objects (NEOs)** from the NASA NEO API
- **Satellite catalog and orbital data** from CelesTrak

The platform provides analysts and engineers with curated views of:

- Potentially hazardous asteroids approaching Earth
- Satellite orbits and catalog changes over time

It is positioned as a **realistic internal platform** rather than a toy demo.

---

## Target Users & Use Cases

### Space Operations / Risk Teams
- Monitor potentially hazardous near-Earth objects
- Track close-approach events and hazard indicators

### Data Science Teams
- Model orbital dynamics
- Analyze hazard probabilities and time-series behavior

### Data Analytics / BI Teams
- Build dashboards on:
  - NEO discovery trends
  - Close-approach statistics
  - Satellite population and orbital distributions

### Platform / Data Engineering
- Demonstrate a solid, production-minded data platform
- Showcase orchestration, observability, and reliability patterns

---

## Core Objectives

### Data Ingestion

Ingest NASA NEO and CelesTrak satellite data via:

- **Batch**
  - Historical backfills
  - Periodic refreshes
- **Streaming**
  - Near-real-time simulation using Kafka

---

### Data Modeling (Medallion Architecture)

- **Bronze**
  - Raw NEO and satellite data
  - As close to source format as possible

- **Silver**
  - Cleaned and normalized entities:
    - NEOs
    - Close-approach events
    - Satellites
    - Orbit snapshots

- **Gold**
  - Business-friendly, analytics-ready tables
  - Optimized for BI and reporting

---

### Orchestration

- End-to-end pipelines orchestrated using **Apache Airflow**
- Includes:
  - Batch DAGs (daily NASA NEO, hourly CelesTrak)
  - Streaming job supervision and monitoring

---

### Analytics Enablement

Enable analytics on:

- NEO hazard indicators and close-approach statistics
- Satellite catalog evolution
- Orbital regime and distribution analysis

---

### Production-Style Practices

Demonstrate realistic platform practices:

- Observability:
  - Structured logging
  - Metrics
  - Monitoring hooks
- Configuration management
- Error handling and retries
- Idempotent pipeline design
- Clear documentation and architecture diagrams

---

## Example Business & Analytical Questions (Gold Layer)

### Near-Earth Objects (NEOs)

- How many NEOs approach Earth within **X lunar distances** per day or week?
- Which upcoming NEOs are flagged as **potentially hazardous** by NASA?
- What is the distribution of:
  - Minimum approach distances
  - Relative velocities over time?
- What are the trends in newly discovered NEOs per month?

---

### Satellites

- How many active satellites exist in each orbital regime:
  - LEO
  - MEO
  - GEO?
- How frequently do **TLE parameters** change for specific satellites?
- Which satellites operated by a given country or operator fall within:
  - Specific inclination ranges?

---

## Scope, Constraints & Assumptions

### Hard Constraints

- **No cloud services**
- Everything runs locally using **Docker only**

### Mandatory Technologies (Dockerized)

- Apache Spark (PySpark)
- Apache Kafka (Zookeeper or KRaft)
- Apache Airflow
- dbt
- PostgreSQL (metadata + warehouse)

**Optional:**
- Prometheus
- Grafana

---

### Data Sources

- **Primary:** NASA NEO API  
  - Near-Earth object feeds and lookups
- **Secondary:** CelesTrak  
  - Satellite catalogs and TLE data (CSV/TXT feeds)

---

### Assumptions

#### Environment
- Single-node / laptop-scale deployment
- ~16 GB RAM recommended (can be tuned down with trade-offs)

#### Data Volume (Approximate)
- NASA NEO:
  - Hundreds of objects per day
  - Manageable for local Spark
- CelesTrak:
  - Tens of thousands of satellite/TLE records
  - Also manageable locally

#### Networking
- Outbound network access available from Docker containers to:
  - NASA APIs
  - CelesTrak endpoints

---

## Explicitly Out of Scope

- Real mission-critical alerting
  - (e.g., notifying real operations centers)
- Highly optimized multi-node cluster tuning
- Complex access control or enterprise-grade security
  - Focus is on **good-practice basics**
