# User Personas & Data Access Patterns

## Space Risk Analyst (Primary BI User)

**Needs:**
- High-level dashboards
- Insights on:
  - Upcoming close approaches
  - Hazard indicators

**Data Access:**
- Queries must be simple and fast
- Consumes **Gold layer views** only

---

## Data Scientist

**Needs:**
- Clean, normalized datasets for modeling
- Analytical-ready structures

**Typical Use Cases:**
- Time series of NEO close-approach distances
- Satellite orbital parameters over time

**Data Access:**
- Reads from the **Silver layer**

---

## Data Engineer / Platform Engineer

**Needs:**
- Observable and reliable pipelines
- Clear operational visibility

**Expectations:**
- Structured logs
- Actionable metrics
- Recoverable and restartable workflows

**Data Access:**
- Works across **all layers** (Bronze, Silver, Gold)
- Owns **infrastructure and orchestration**

---

## Portfolio Reviewer / Hiring Manager

**Wants to See:**
- Clean, readable, well-structured code
- Clear and intentional architecture
- Correct and effective use of:
  - Spark
  - Kafka
  - Airflow
  - dbt
  - Postgres
- Production-style:
  - Logging
  - Monitoring
  - Documentation

---

## Persona ↔ Data Layer Mapping

| Persona                        | Primary Data Layer |
|--------------------------------|--------------------|
| Space Risk Analyst             | Gold               |
| Data Scientist                 | Silver             |
| Data Engineer / Platform Eng.  | All + Infrastructure |
| Portfolio Reviewer / Manager   | Architecture & Docs |
