# Business & Functional Test Cases – Space Objects Data Platform

> **Status:** Living document
> **Audience:** Product owner, business analysts, QA, and reviewers validating that the platform
> delivers real analytical value — not that the code compiles.
> **Prerequisite reading:** [scope.md](scope.md), [use_cases.md](use_cases.md), [personas.md](personas.md), [data_flow.md](data_flow.md).

These are **functional / business acceptance tests**. Each test states the **business question or
outcome** it validates, **why it matters** (what real problem it resolves), the **scenario**
(Given / When / Then), and a **verification** the platform can actually answer it. They deliberately
avoid syntax-level, unit, or schema-shape checks — those live with the engineering tests.

---

## 1. What This Project Resolves (Problem → Capability Map)

| Real-world problem | Who has it | Platform capability that resolves it | Gold/ML asset |
|---|---|---|---|
| "We can't see which asteroids are about to pass close to Earth, or how dangerous they are." | Space risk / operations analyst | Curated daily close-approach + hazard view | `gold.neo_daily_activity`, `gold.neo_hazard_summary` |
| "Hazard assessment is manual and inconsistent across analysts." | Risk team lead | Standardized hazard flags + ML risk score | `gold.neo_hazard_summary`, `ml.prediction` (UC-1) |
| "We don't have a clean, modelled satellite catalog to analyze orbital populations." | Data scientist / analyst | Normalized satellite + orbit snapshot tables | `silver.satcat_satellite`, `gold.satcat_orbit_summary` |
| "We can't tell how the satellite population is distributed across orbital regimes." | Analytics / BI | Orbit regime roll-ups & classification | `gold.satcat_orbit_summary`, `ml.prediction` (UC-2) |
| "We can't spot satellites whose orbits are decaying or behaving abnormally." | Operations | Orbital anomaly detection | `ml.prediction` (UC-3) |
| "Reports take too long / data is stale when decisions are made." | All consumers | Orchestrated, monitored, fresh pipelines | Airflow DAGs, `meta.pipeline_run` |
| "We can't trust the numbers — are records complete and valid?" | Data engineer / analyst | Data-quality gates with audit trail | `meta.data_quality_run` |
| "When something breaks, nobody notices until a stakeholder complains." | Platform engineer | Pipeline + streaming supervision & metrics | `streaming_supervision_dag`, Prometheus/Grafana |

---

## 2. Test Conventions

- **ID format:** `BT-<area>-<n>` (NEO, SAT, ML, DQ, OPS, FRESH, E2E).
- **Priority:** P0 = core promise of the platform; P1 = important; P2 = nice-to-have.
- **Result evidence:** a query result, dashboard panel, or DAG run state a business user can inspect.
- **Pass criteria** are written so a non-engineer can confirm them.
- Example queries are illustrative; exact column names are in the gold/silver models.

---

## 3. NEO — Near-Earth Object Hazard Awareness

### BT-NEO-1 — Identify potentially hazardous asteroids approaching Earth (P0)

- **Business question:** "Which upcoming near-Earth objects are flagged as potentially hazardous?"
- **Why it matters:** This is the platform's headline promise — giving risk analysts an at-a-glance
  list of dangerous approaches so they can prioritize attention.
- **Scenario**
  - **Given** NEO data has been ingested and processed through to the gold layer,
  - **When** an analyst queries `gold.neo_hazard_summary` for objects flagged hazardous,
  - **Then** the result returns one row per hazardous NEO with its closest approach distance and approach count.
- **Verification**
  ```sql
  SELECT neo_id, name, total_approaches, closest_miss_distance_km, is_potentially_hazardous
  FROM gold.neo_hazard_summary
  WHERE is_potentially_hazardous = true
  ORDER BY closest_miss_distance_km ASC;
  ```
- **Pass criteria:** Hazardous NEOs are listed and sortable by how close they come; no hazardous
  object known in the source is missing from the list.

### BT-NEO-2 — Count close approaches within a distance threshold per day/week (P0)

- **Business question:** "How many NEOs approach Earth within X lunar distances per day or week?"
- **Why it matters:** Lets risk teams quantify activity volume and spot unusually busy windows.
- **Scenario**
  - **Given** processed close-approach facts exist,
  - **When** an analyst filters `gold.neo_daily_activity` (or `silver.neo_close_approach`) by a
    lunar-distance threshold and date range,
  - **Then** the platform returns per-day counts within that threshold.
- **Verification**
  ```sql
  SELECT close_approach_date, COUNT(*) AS approaches_within_5_ld
  FROM silver.neo_close_approach
  WHERE miss_distance_lunar <= 5
  GROUP BY close_approach_date
  ORDER BY close_approach_date;
  ```
- **Pass criteria:** Returns a daily time series; changing the threshold (e.g. 1 vs 10 LD)
  proportionally changes the counts in a sensible direction.

### BT-NEO-3 — Rank the riskiest upcoming approaches (P0)

- **Business question:** "Of everything approaching, what should I look at first?"
- **Why it matters:** Converts raw data into a prioritized worklist — the core analyst workflow.
- **Scenario**
  - **Given** hazard summary and approach facts are populated,
  - **When** the analyst requests the top-N approaches ordered by closeness (and optionally hazard flag),
  - **Then** the platform returns a ranked shortlist.
- **Verification**
  ```sql
  SELECT n.name, ca.close_approach_date, ca.miss_distance_lunar, ca.rel_velocity_km_s,
         n.is_potentially_hazardous_asteroid
  FROM silver.neo_close_approach ca
  JOIN silver.neo n ON ca.neo_id = n.neo_id
  ORDER BY ca.miss_distance_lunar ASC
  LIMIT 20;
  ```
- **Pass criteria:** The closest / fastest / hazardous objects rise to the top of the list.

### BT-NEO-4 — Distribution of approach distances and velocities over time (P1)

- **Business question:** "What is the distribution of minimum approach distances and relative
  velocities over time?"
- **Why it matters:** Supports trend analysis and detecting shifts in approach behavior.
- **Scenario**
  - **Given** multiple days of approach facts,
  - **When** an analyst aggregates distance/velocity statistics by period,
  - **Then** the platform returns min / avg / max bands suitable for charting.
- **Verification**
  ```sql
  SELECT close_approach_date,
         MIN(miss_distance_lunar) AS min_ld,
         AVG(rel_velocity_km_s)   AS avg_velocity,
         MAX(rel_velocity_km_s)   AS max_velocity
  FROM silver.neo_close_approach
  GROUP BY close_approach_date
  ORDER BY close_approach_date;
  ```
- **Pass criteria:** Returns plottable bands; values stay within physically plausible ranges.

### BT-NEO-5 — Newly discovered NEO trend (P2)

- **Business question:** "What are the trends in newly discovered NEOs per month?"
- **Why it matters:** Helps leadership understand catalog growth and monitoring load.
- **Scenario**
  - **Given** NEO dimension records carry first-seen information,
  - **When** an analyst groups discoveries by month,
  - **Then** the platform returns a monthly discovery trend.
- **Pass criteria:** A monthly series is produced; spikes correspond to real ingestion windows.

---

## 4. Satellite Catalog & Orbital Population

### BT-SAT-1 — Satellite counts by orbital regime (P0)

- **Business question:** "How many satellites exist in each orbital regime (LEO / MEO / GEO / HEO)?"
- **Why it matters:** Foundational situational-awareness metric for space operations and policy.
- **Scenario**
  - **Given** satellite catalog and orbit snapshots are processed to gold,
  - **When** an analyst groups satellites by derived orbit regime,
  - **Then** the platform returns counts per regime.
- **Verification**
  ```sql
  SELECT orbit_regime, COUNT(*) AS satellite_count
  FROM gold.satcat_orbit_summary
  GROUP BY orbit_regime
  ORDER BY satellite_count DESC;
  ```
- **Pass criteria:** Every active satellite is assigned to exactly one regime; LEO dominates the
  population (sanity check against reality).

### BT-SAT-2 — Satellites by operator / owner within an inclination band (P1)

- **Business question:** "Which satellites operated by a given country/operator fall within specific
  inclination ranges?"
- **Why it matters:** Supports ownership/coverage analysis and regulatory questions.
- **Scenario**
  - **Given** satellite dimension carries owner and orbit snapshots carry inclination,
  - **When** an analyst filters by owner and an inclination band,
  - **Then** the platform returns the matching satellites.
- **Verification**
  ```sql
  SELECT s.object_name, s.owner, o.inclination_deg
  FROM silver.satcat_satellite s
  JOIN silver.satcat_orbit_snapshot o ON s.norad_cat_id = o.norad_cat_id
  WHERE s.owner = 'US' AND o.inclination_deg BETWEEN 50 AND 60
  ORDER BY o.inclination_deg;
  ```
- **Pass criteria:** Filter returns only satellites matching both owner and inclination band.

### BT-SAT-3 — Orbital characteristics roll-up per satellite (P1)

- **Business question:** "What are the orbital characteristics (period, apogee, perigee, inclination)
  of a given satellite?"
- **Why it matters:** Gives data scientists a clean per-satellite profile for modelling.
- **Verification**
  ```sql
  SELECT norad_cat_id, object_name, period_minutes, apogee_km, perigee_km, inclination_deg
  FROM gold.satcat_orbit_summary
  WHERE norad_cat_id = 25544;   -- e.g. ISS
  ```
- **Pass criteria:** Returns a coherent orbital profile; values are physically plausible
  (e.g. perigee ≤ apogee, LEO period ≈ 90 min).

### BT-SAT-4 — Track how often a satellite's orbit changes over time (P2)

- **Business question:** "How frequently do orbital parameters change for specific satellites?"
- **Why it matters:** Indicates manoeuvres or decay; supports operations monitoring.
- **Scenario**
  - **Given** multiple orbit snapshots exist per satellite over time,
  - **When** an analyst inspects the snapshot history for a satellite,
  - **Then** changes in period/apogee/perigee across dates are visible.
- **Pass criteria:** A multi-row history is returned for satellites with repeated snapshots, ordered
  by snapshot date.

---

## 5. AI/ML-Driven Decision Support
*(Validates the AI workstream from [ai_implementation.md](ai_implementation.md). Run once those phases are delivered.)*

### BT-ML-1 — Automated hazard risk score for every approach (P1)

- **Business question:** "Beyond the binary NASA flag, can the platform give a consistent risk score
  to prioritize approaches?"
- **Why it matters:** Standardizes triage and removes analyst-to-analyst inconsistency.
- **Scenario**
  - **Given** the NEO hazard model (UC-1) is trained and active and inference has run,
  - **When** an analyst reads `ml.prediction` for NEOs,
  - **Then** each scored approach has a probability/score usable for ranking.
- **Verification**
  ```sql
  SELECT p.entity_key, p.predicted_label, p.predicted_score
  FROM ml.prediction p
  JOIN ml.model_registry m ON p.model_id = m.model_id
  WHERE m.model_name = 'neo_hazard_classifier' AND m.is_active
  ORDER BY p.predicted_score DESC
  LIMIT 20;
  ```
- **Pass criteria:** Every feature row has a score; high scores align with known-hazardous objects.

### BT-ML-2 — Model quality meets the business acceptance bar (P1)

- **Business question:** "Is the deployed model good enough to rely on?"
- **Why it matters:** Prevents an unreliable model from driving decisions.
- **Verification**
  ```sql
  SELECT metric_name, metric_value
  FROM ml.model_metric mm
  JOIN ml.model_registry m ON mm.model_id = m.model_id
  WHERE m.model_name = 'neo_hazard_classifier' AND m.is_active
    AND mm.dataset_split = 'test';
  ```
- **Pass criteria:** Active model's test `roc_auc` ≥ agreed threshold (e.g. 0.70); if below, the
  training DQ gate should have prevented activation (cross-check `meta.data_quality_run`).

### BT-ML-3 — Orbit regime classification agrees with rule-based regime (P2)

- **Business question:** "Can the platform automatically classify a satellite's orbital regime?"
- **Why it matters:** Enables regime analytics even when raw fields are incomplete.
- **Pass criteria:** Predicted regime matches the rule-derived regime for the large majority of
  satellites (agreement ≥ agreed threshold).

### BT-ML-4 — Surface anomalous / decaying satellites (P2)

- **Business question:** "Which satellites are behaving abnormally and warrant a closer look?"
- **Why it matters:** Early warning for decay or manoeuvres without manual scanning.
- **Pass criteria:** Anomaly model returns a ranked shortlist; top entries show genuinely large
  orbit-parameter deltas versus their own history.

---

## 6. Data Quality & Trust

### BT-DQ-1 — Records pass validation before reaching analysts (P0)

- **Business question:** "Can I trust that the data feeding my decisions is valid and complete?"
- **Why it matters:** Bad data silently corrupts every downstream report and model.
- **Scenario**
  - **Given** a bronze→silver Spark job has run,
  - **When** a data engineer reviews `meta.data_quality_run` for that run,
  - **Then** key DQ checks (non-null keys, uniqueness, valid ranges) are recorded with pass/fail counts.
- **Verification**
  ```sql
  SELECT check_name, status, total_records, failed_records
  FROM meta.data_quality_run
  ORDER BY created_at DESC
  LIMIT 20;
  ```
- **Pass criteria:** Critical checks are present and `status='pass'`; any failures are quantified and
  traceable to a pipeline run.

### BT-DQ-2 — No duplicate business entities reach the curated layers (P0)

- **Business question:** "Am I double-counting asteroids or satellites?"
- **Why it matters:** Duplicates inflate counts and distort hazard/population metrics.
- **Verification**
  ```sql
  SELECT neo_id, COUNT(*) FROM silver.neo GROUP BY neo_id HAVING COUNT(*) > 1;          -- expect 0 rows
  SELECT norad_cat_id, COUNT(*) FROM silver.satcat_satellite GROUP BY norad_cat_id HAVING COUNT(*) > 1; -- expect 0 rows
  ```
- **Pass criteria:** Both queries return zero rows.

### BT-DQ-3 — Gold metrics reconcile with their silver sources (P1)

- **Business question:** "Do the headline numbers actually tie back to the underlying data?"
- **Why it matters:** Builds stakeholder confidence; catches transformation errors.
- **Pass criteria:** Aggregations in gold (e.g. total approaches) reconcile within tolerance to the
  same aggregation computed directly from silver facts.

---

## 7. Data Freshness & Timeliness

### BT-FRESH-1 — Batch data is no more than 24h behind source (P0)

- **Business question:** "Is the data current enough to act on?"
- **Why it matters:** Stale hazard data is operationally useless. Scope sets a <24h batch SLA.
- **Scenario**
  - **Given** daily batch DAGs run on schedule,
  - **When** a user checks the latest ingestion timestamp,
  - **Then** the most recent data is within the freshness SLA.
- **Verification**
  ```sql
  SELECT MAX(ingestion_timestamp) AS latest_ingest,
         now() - MAX(ingestion_timestamp) AS lag
  FROM bronze.nasa_neo_event_raw;
  ```
- **Pass criteria:** Lag for batch sources < 24h; (streaming target < 30 min per scope SLA).

### BT-FRESH-2 — Gold layer reflects the latest successful pipeline run (P1)

- **Business question:** "When I open a dashboard, am I seeing today's run?"
- **Why it matters:** Prevents decisions on yesterday's numbers.
- **Pass criteria:** Latest `meta.pipeline_run` for the gold/dbt job is `success` and its end time is
  recent; gold tables reflect that run.

---

## 8. Operational Reliability (Platform Promise)

### BT-OPS-1 — End-to-end pipeline completes successfully on schedule (P0)

- **Business question:** "Does the whole pipeline run reliably without manual babysitting?"
- **Why it matters:** Reliability is a core portfolio/operations promise.
- **Scenario**
  - **Given** Airflow is running,
  - **When** the daily DAG chain (ingest → silver → gold) executes,
  - **Then** all DAGs finish `success` with no manual intervention.
- **Verification:** Airflow UI shows green runs for `neo_batch_dag`, `celestrak_batch_dag`,
  `bronze_to_silver_dag`, `dbt_gold_dag`; cross-check `meta.pipeline_run`.
- **Pass criteria:** Full chain green for the day; failures (if any) auto-retried per DAG config.

### BT-OPS-2 — Re-running a pipeline does not corrupt or duplicate data (P0)

- **Business question:** "If a job re-runs after a hiccup, is the data still correct?"
- **Why it matters:** Idempotency is what makes recovery safe.
- **Scenario**
  - **Given** a batch/silver job has already loaded a window,
  - **When** the same job is re-run for the same window,
  - **Then** counts are unchanged (no duplicates, no loss).
- **Pass criteria:** Row counts identical before/after re-run; BT-DQ-2 still passes.

### BT-OPS-3 — Streaming stalls are detected (P1)

- **Business question:** "If a real-time feed silently stops, will we know?"
- **Why it matters:** Undetected streaming failure = blind spot in situational awareness.
- **Scenario**
  - **Given** `streaming_supervision_dag` runs every 10 minutes,
  - **When** a streaming producer goes stale,
  - **Then** the supervision job flags it (via `meta.pipeline_run` state / alerting).
- **Pass criteria:** A stale/failed streaming run is surfaced rather than passing silently.

### BT-OPS-4 — Operational health is visible without reading code (P1)

- **Business question:** "Can an operator see system health at a glance?"
- **Why it matters:** Self-service observability reduces time-to-detect.
- **Pass criteria:** Grafana shows live Kafka/Postgres metrics; pipeline run history is queryable in
  `meta.pipeline_run`.

---

## 9. End-to-End Business Scenarios

### BT-E2E-1 — "Daily hazard briefing" walk-through (P0)

- **Outcome validated:** A risk analyst can, in one sitting, answer "what's approaching, how close,
  and how dangerous?" entirely from the gold layer.
- **Scenario**
  1. **Given** the daily pipeline has completed successfully,
  2. **When** the analyst opens the NEO hazard view and filters to the next 7 days within a chosen
     lunar-distance threshold,
  3. **And** sorts by closeness / hazard flag (and, if available, ML risk score),
  4. **Then** they obtain a ranked, trustworthy shortlist with distance, velocity, and hazard status.
- **Pass criteria:** The shortlist is produced in a single workflow, returns quickly (per scope,
  typical queries < 5–10s locally), and every listed object reconciles to source data.

### BT-E2E-2 — "Satellite population snapshot" walk-through (P1)

- **Outcome validated:** An analyst can produce a current breakdown of the satellite population by
  regime and operator for a briefing.
- **Scenario**
  1. **Given** the catalog pipeline has completed,
  2. **When** the analyst groups satellites by orbital regime and by operator,
  3. **Then** they obtain population counts and distributions suitable for a slide.
- **Pass criteria:** Counts are internally consistent (regime totals sum to the active population)
  and match sanity expectations (LEO largest).

### BT-E2E-3 — "Recovery without data loss" walk-through (P1)

- **Outcome validated:** The platform survives a mid-pipeline failure and recovers cleanly.
- **Scenario**
  1. **Given** a DAG fails partway,
  2. **When** it is retried/re-run,
  3. **Then** the pipeline completes and downstream metrics are correct (no dupes, no gaps).
- **Pass criteria:** BT-OPS-2 + BT-DQ-2 hold after recovery; final gold metrics match a clean run.

---

## 10. Traceability — Business Test ↔ Source Requirement

| Test | Source requirement (doc) |
|---|---|
| BT-NEO-1..5 | [scope.md](scope.md) "Example Business & Analytical Questions – NEOs", [use_cases.md](use_cases.md) |
| BT-SAT-1..4 | [scope.md](scope.md) "Example Business & Analytical Questions – Satellites" |
| BT-ML-1..4 | [ai_implementation.md](ai_implementation.md) UC-1..UC-3 |
| BT-DQ-1..3 | [use_cases.md](use_cases.md) "Data Quality" KPIs |
| BT-FRESH-1..2 | [use_cases.md](use_cases.md) "Data Freshness" SLA |
| BT-OPS-1..4 | [use_cases.md](use_cases.md) "Pipeline Reliability", [architecture_principles.md](architecture_principles.md) "Observability" |
| BT-E2E-1..3 | [use_cases.md](use_cases.md) "Ability to run predefined example reports" |

---

## 11. How to Use This Document

- **Acceptance / demo:** Walk BT-E2E-1..3 to prove the platform's value story to a stakeholder.
- **Regression confidence:** Run the P0 tests after any pipeline change before declaring "done".
- **Definition of value-done:** A feature is business-complete only when its associated BT cases pass
  and the evidence (query result / dashboard / green DAG) can be shown to a non-engineer.
