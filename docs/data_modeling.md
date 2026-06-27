# Data Modeling – Space Objects Data Platform

> **Status:** Reference / design rationale (describes the *implemented* silver + gold model and the modeling choices behind it).
> **Audience:** Anyone extending the warehouse — especially the engineer picking up the AI/ML workstream.
> **Prerequisite reading:** [scope.md](scope.md), [architecture_principles.md](architecture_principles.md), [data_flow.md](data_flow.md), [source_data.md](source_data.md).

This document explains **how** the platform models its data for two distinct consumption patterns —
**Business Intelligence (BI)** and **Artificial Intelligence / Machine Learning (AI)** — and, just as
importantly, **why** each model was chosen, what **real-world scenario** it serves, what **benefits**
it delivers, and **why competing modeling approaches were rejected**.

The guiding idea: **one clean, normalized silver foundation; two purpose-built gold shapes on top.**

---

## 1. Modeling Philosophy

### 1.1 Two consumers, two access patterns

| Concern | BI consumer | AI/ML consumer |
|---|---|---|
| Typical query | Aggregations, group-bys, trends, filters | Full-table scan of one wide row per training example |
| Grain needed | Roll-ups (per day, per object, per regime) | Atomic event/snapshot, one row = one observation |
| Shape preferred | Star schema (facts + dimensions), pre-aggregated marts | Denormalized flat feature matrix with a label |
| Optimized for | Human readability, dashboard latency, slicing | `pandas.read_sql` → `scikit-learn` `fit/predict` |
| Stability needed | Conformed business definitions | Reproducible, leakage-free feature/label contract |

A single table cannot serve both well. BI wants *narrow, conformed, aggregated*; ML wants *wide, atomic,
flat*. So the gold layer **forks** into two families that share the same silver source of truth.

### 1.2 Layered (medallion) backbone

```
Bronze (raw, source-shaped JSONB)
   │  Spark: parse, normalize, dedupe, DQ
   ▼
Silver (normalized entities — the conformed core)   ← single source of truth
   │
   ├── dbt → Gold BI marts        (star schema + aggregated marts)
   └── dbt → Gold AI feature tables (flat, atomic, labeled)
```

Silver is modeled **once**, correctly, as conformed dimensions and facts. Both gold families are
**views of intent** built from the same silver tables, guaranteeing that a number on a BI dashboard and
a feature fed to a model are derived from the *same* governed definitions.

---

## 2. The Conformed Core (Silver) — Shared Foundation

Before BI vs. AI diverge, they agree on the same four normalized entities. These are physical,
Spark-managed tables (see [infra/postgres/init.sql](../infra/postgres/init.sql)).

### 2.1 Entity-relationship overview

```
        silver.neo (dimension)                 silver.satcat_satellite (dimension)
         neo_sk  (PK)                            satellite_sk (PK)
         neo_id  (NK)                            norad_cat_id (NK)
            │ 1                                       │ 1
            │                                         │
            │ N                                       │ N
        silver.neo_close_approach (fact)        silver.satcat_orbit_snapshot (fact)
         approach_sk (PK)                         orbit_snapshot_sk (PK)
         neo_sk (FK) ─────────────────┘           satellite_sk (FK) ──────────────┘
         grain: 1 close-approach event            grain: 1 orbital snapshot per satellite per date
```

### 2.2 Why two facts + two dimensions (classic dimensional split)

- **Dimensions describe "the thing" (slowly changing):** an asteroid (`silver.neo`) and a satellite
  (`silver.satcat_satellite`) each have stable descriptive attributes (name, magnitude, owner, object
  type, launch date).
- **Facts describe "an event/measurement about the thing" (fast-growing):** a close-approach event
  (`silver.neo_close_approach`) and an orbital snapshot (`silver.satcat_orbit_snapshot`) carry the
  numeric measures (velocity, miss distance, period, inclination, apogee, perigee) at a point in time.

This separation is deliberate: descriptive attributes are stored **once** per object, while
measurements accumulate over time **without duplicating** the descriptive context. It directly enables
both consumer shapes downstream — BI joins facts to dimensions for slicing; AI joins them to assemble a
flat feature row.

**Grain is explicit and enforced by natural keys:**
- `neo_close_approach`: `UNIQUE (neo_id, close_approach_date_full, orbiting_body)`
- `satcat_orbit_snapshot`: `UNIQUE (norad_cat_id, snapshot_date)`

Declaring grain via a uniqueness constraint is what makes both downstream marts trustworthy — counts
don't double, and one feature row really is one observation.

### 2.3 Surrogate keys (`neo_sk`, `satellite_sk`, `approach_sk`, `orbit_snapshot_sk`)

Each table carries a Postgres-sequence surrogate key **in addition to** the source natural key.

- **Why:** decouples the warehouse from source-key volatility, gives facts a compact integer FK to
  their dimension, and yields a stable per-row identifier (`approach_sk`, `orbit_snapshot_sk`) that the
  AI layer reuses as the **feature-row id** (and later as `snapshot_ref` in `ml.prediction`).
- **Why not natural keys alone:** NASA/CelesTrak identifiers are text, can change format, and are not
  guaranteed stable; using them as the only join/identity key couples the model to source quirks.

---

## 3. BI Data Modeling

### 3.1 Selected model: **Dimensional (Kimball star schema) + pre-aggregated marts**

The gold BI layer is a small **star schema** plus a few **aggregated marts** materialized as tables by
dbt ([dbt/space_objects/models/gold](../dbt/space_objects/models/gold)).

| Gold table | Type | Grain | Source |
|---|---|---|---|
| [neo_daily_activity.sql](../dbt/space_objects/models/gold/neo_daily_activity.sql) | Aggregated mart | 1 row per `close_approach_date` | `neo_close_approach` × `neo` |
| [neo_hazard_summary.sql](../dbt/space_objects/models/gold/neo_hazard_summary.sql) | Aggregated mart | 1 row per `neo_id` | `neo_close_approach` × `neo` |
| [satcat_orbit_summary.sql](../dbt/space_objects/models/gold/satcat_orbit_summary.sql) | Aggregated mart | 1 row per `norad_cat_id` | `satcat_satellite` × `satcat_orbit_snapshot` |

These sit on top of the conformed silver star (facts + dimensions of §2). dbt's silver models are
**ephemeral** (inline CTEs), so the marts compile down to direct reads of the Spark-managed silver
tables — no duplicate physical silver objects.

### 3.2 Why dimensional modeling was selected

1. **Matches the questions being asked.** Every BI question in [scope.md](scope.md) is a slice-and-dice
   over events by a descriptive attribute or time:
   - *"How many NEOs approach within X lunar distances per day?"* → aggregate the close-approach **fact**
     by **date**.
   - *"Which upcoming NEOs are potentially hazardous?"* → filter the **fact** by a **dimension** flag.
   - *"How many satellites per orbital regime / operator?"* → group the orbit **fact**/dimension by a
     **dimension** attribute.
   Star schemas are the canonical, lowest-friction shape for exactly this group-by-and-filter pattern.

2. **Human-readable and self-describing.** Conformed dimensions (`name`, `owner`, `object_type`,
   `is_potentially_hazardous_asteroid`) read naturally in a Grafana/SQL query without the analyst
   needing to know JSONB paths or source quirks.

3. **Dashboard performance at laptop scale.** Pre-aggregating into `*_daily_activity` / `*_summary`
   marts means the dashboard reads a few thousand pre-computed rows instead of scanning 300K+ raw
   snapshots — keeping the scope.md target of *"<5–10s for typical queries on a modest local machine"*
   easily achievable.

4. **Conformed definitions = one version of the truth.** "Hazardous", "closest approach", and "snapshot
   count" are defined **once** in dbt and tested (51 dbt tests: not-null/unique/accepted-values), so
   every dashboard agrees.

### 3.3 Real-world scenario per BI mart

- **`neo_daily_activity` — Planetary-defense situational dashboard.**
  *Scenario:* a risk/operations analyst opens a daily dashboard each morning to see "how busy is the sky
  today?" — total approaches, distinct objects, and how many were hazardous, plotted as a time series.
  This is the platform's headline operational view.

- **`neo_hazard_summary` — Per-object watchlist.**
  *Scenario:* an analyst investigating a specific asteroid needs its closest-ever approach (km), how many
  times it has approached, its activity window (first/last approach), and whether NASA flags it
  hazardous. One row per object = a clean watchlist / drill-down target.

- **`satcat_orbit_summary` — Space-situational-awareness population view.**
  *Scenario:* an SSA/BI analyst characterizes the catalog — average period/inclination/apogee/perigee per
  satellite, snapshot history depth, owner and object type — to answer population and orbital-distribution
  questions (e.g., UAE-owned assets, LEO congestion). Maps directly to UAE Space Agency / MBRSC use cases
  in [source_celestrak.md](source_celestrak.md).

### 3.4 Benefits of the BI model

- **Low query complexity** for analysts (no JSONB, no window gymnastics for common questions).
- **Fast** dashboards via pre-aggregation; predictable, small result sets.
- **Governed & tested** business metrics (dbt tests guard grain and domains).
- **Extensible:** new marts are additive dbt models over the same conformed star — no silver rework.
- **Tool-agnostic:** plain relational star works with Grafana, any SQL client, or a future BI tool.

### 3.5 Alternatives considered and why they were rejected

| Alternative | What it is | Why **not** chosen here |
|---|---|---|
| **3NF / fully normalized warehouse** | Highly normalized, many small tables, no redundancy | Forces analysts to write multi-join queries for every question; slower dashboards; optimizes for write-integrity (an OLTP concern) when this is a read-heavy analytics store. Integrity already handled in silver. |
| **One Big Table (OBT) / fully denormalized mart** | Single mega-table joining everything | Explodes storage by repeating dimension attributes across every event row; ambiguous grain; hard to keep metric definitions consistent; awkward for "per object" vs "per day" questions simultaneously. (We *do* use a flat shape — but only for AI, §4, where it's the right tool.) |
| **Data Vault (hubs/links/satellites)** | Insert-only, audit-heavy, source-agnostic integration model | Massive structural overhead for a 2-source, laptop-scale, portfolio platform; query layer would still need a star on top. Cost ≫ benefit at this scale. |
| **Snowflake schema** (normalized dimensions) | Dimensions split into sub-dimensions | Our dimensions are small and flat; snowflaking adds joins and complexity for no storage win at this volume. |
| **Cubes / pre-built OLAP engine** | Dedicated MOLAP cube store | Violates the "PostgreSQL is the single warehouse / no extra storage systems" rule in [architecture_principles.md](architecture_principles.md); unnecessary for the data volume. |

**Net:** Kimball star + thin aggregated marts is the **minimum sufficient** model for the BI questions in
scope, while respecting the single-warehouse, laptop-scale constraints.

---

## 4. AI Data Modeling

### 4.1 Selected model: **Flat, atomic, labeled feature tables (one row per observation)**

The gold AI layer is two **denormalized feature tables**, each a flat join of a fact to its dimension at
the **fact's native grain**, with identifiers and (where supervised) a **label** column.

| Feature table | Grain (1 row =) | Feature columns | Label |
|---|---|---|---|
| [ai_neo_features.sql](../dbt/space_objects/models/gold/ai_neo_features.sql) | one close-approach event (`approach_sk`) | `rel_velocity_km_s`, `rel_velocity_km_h`, `miss_distance_km`, `miss_distance_lunar`, `miss_distance_au`, `absolute_magnitude_h` | `is_hazardous_label` (0/1) |
| [ai_satcat_features.sql](../dbt/space_objects/models/gold/ai_satcat_features.sql) | one orbit snapshot (`orbit_snapshot_sk`) | `period_minutes`, `inclination_deg`, `apogee_km`, `perigee_km`, `object_type`, `owner` | (label derived later, e.g. orbit regime) |

Each row carries: a **stable surrogate id** (the feature-row key), the **business key** (`neo_id` /
`norad_cat_id`), a **time anchor** (`close_approach_date` / `snapshot_date`), the **features**, and (for
supervised cases) the **label** — exactly the contract a `scikit-learn` pipeline expects after
`pandas.read_sql`.

### 4.2 Why a flat, atomic feature table was selected

1. **It is the native shape of supervised ML.** Training expects a 2-D design matrix `X` (one row per
   example, one column per feature) plus a label vector `y`. A flat table maps **1:1** onto
   `df[features]` / `df[label]` with no reshaping — minimizing the code between SQL and `model.fit()`.

2. **Atomic grain preserves signal.** ML learns from *individual* observations, not roll-ups. Keeping one
   row per close-approach event / per orbit snapshot retains the full distribution of velocities, miss
   distances, and orbital parameters that the model needs. Aggregating (the BI move) would destroy the
   per-event variance the model is supposed to learn from.

3. **Denormalization removes train-time joins.** Folding the few needed dimension attributes
   (`absolute_magnitude_h`; `object_type`, `owner`) into the fact row means the trainer issues a single
   `SELECT * FROM gold.ai_*_features` — no joins, no JSONB parsing, reproducible every run.

4. **Feature engineering lives in dbt (SQL), not Python.** Per [ai_implementation.md](ai_implementation.md)
   ("dbt for features only"), the feature contract is versioned, tested, and shared. Python ML code
   *consumes* features; it does not re-derive them — preventing train/serve skew.

5. **Stable per-row id enables prediction write-back.** `approach_sk` / `orbit_snapshot_sk` become the
   `snapshot_ref` in `ml.prediction`, so every score is traceable back to the exact feature row and to the
   model version that produced it.

### 4.3 Real-world scenario per AI feature table

- **`ai_neo_features` — Hazard classification (UC-1).**
  *Scenario:* train a binary classifier to predict `is_potentially_hazardous` from approach/orbital
  features, then batch-score upcoming approaches so the ops dashboard can rank "top-risk upcoming NEOs."
  This feature row also supports the more honest derived target suggested in
  [ai_implementation.md](ai_implementation.md) (e.g., "approach within N lunar distances next window")
  because it already carries `miss_distance_lunar` and velocity at the atomic grain.

- **`ai_satcat_features` — Orbit-regime classification, anomaly detection, clustering (UC-2/3/5).**
  *Scenario:* classify each satellite snapshot into LEO/MEO/GEO/HEO from `period/inclination/apogee/perigee`;
  cluster the population into constellations/orbital families; or detect snapshots that deviate from a
  satellite's own history. The per-snapshot grain is essential for the time-aware UC-3 (deltas vs. prior
  snapshot) and for population clustering in UC-5.

### 4.4 Benefits of the AI model

- **Minimal glue code:** SQL → DataFrame → `fit/predict` with no reshaping.
- **Reproducible & leakage-aware:** the feature/label contract is explicit, tested, and identical at
  train and inference time (same dbt model feeds both).
- **Versioned features:** changing a feature is a reviewed dbt change with tests, not a hidden Python tweak.
- **Reusable scaffolding:** every model (UC-1…UC-5) consumes the same flat-table pattern, so the
  training/inference/registry plumbing is written once and copied.
- **Traceable predictions:** surrogate-key feature ids tie each `ml.prediction` row back to its features
  and model version.

### 4.5 Alternatives considered and why they were rejected

| Alternative | What it is | Why **not** chosen here |
|---|---|---|
| **Train directly off bronze JSONB** | Point the model loader at raw `bronze.*` tables | Forces every training run to parse JSONB, dedupe, and cast — slow, fragile, and a prime source of train/serve skew. Cleaning belongs upstream (silver), not in the model. |
| **Train off the BI aggregated marts** | Reuse `neo_daily_activity` / `*_summary` | Wrong grain: aggregation has already collapsed the per-event signal the model must learn from. Daily counts can't classify an individual asteroid. |
| **Normalized features (join at train time)** | Keep features split across fact + dimension, join in Python | Reintroduces joins and JSONB handling into the ML path; higher skew risk; slower; more code. Denormalizing a *handful* of attributes into the feature row is cheaper and safer. |
| **Dedicated external feature store (Feast, etc.)** | Separate online/offline feature service | Adds a whole subsystem and storage engine, violating the single-warehouse / no-extra-infra constraints; unjustified for laptop scale and a handful of models. dbt tables + the planned `ml` schema are sufficient. |
| **Heavy feature engineering in Python/Spark** | Compute features imperatively in the trainer | Splits the feature definition across code paths, breaks reproducibility, and contradicts the "dbt for features only" guardrail. SQL features are inspectable, testable, and shared. |
| **One wide OBT shared with BI** | Single mega-table serving both BI and ML | BI needs narrow/aggregated; ML needs wide/atomic — a shared OBT serves neither well and blurs grain. Keeping two purpose-built gold shapes is cleaner. |

**Net:** A flat, atomic, dbt-built feature table is the **right-sized** ML contract: it gives models the
signal-preserving, reproducible, low-glue input they need without importing external feature-store
infrastructure.

---

## 5. Why the BI and AI Models Diverge (Side-by-Side)

| Dimension | BI gold (star + marts) | AI gold (flat feature tables) |
|---|---|---|
| Grain | Aggregated (per day / per object) | Atomic (per event / per snapshot) |
| Shape | Conformed dimensions + facts, pre-aggregated | Denormalized single row per observation |
| Optimized for | Human slicing, dashboard latency | `fit/predict`, reproducibility |
| Joins at consume time | Yes (star joins, but small) | No (pre-joined/denormalized) |
| Label column | No | Yes (supervised cases) |
| Aggregation | Embraced (the point) | Avoided (destroys signal) |
| Consumer | Grafana / SQL analyst | scikit-learn / pandas |
| Source of truth | Same conformed silver | Same conformed silver |

The fork is intentional and is the core modeling decision of this document: **separate gold shapes for
separate access patterns, both governed by one silver core.**

---

## 6. Cross-Cutting Modeling Decisions

- **JSONB confined to bronze.** Nested source structures (`relative_velocity`, `miss_distance`,
  `estimated_diameter`, `parsed_record`) are flattened into typed columns in silver, so neither BI nor AI
  consumers ever touch JSON. *Why:* typed columns are testable, indexable, and tool-friendly; JSON in the
  serving layer is a recurring source of skew and bugs.
- **Grain declared as a uniqueness constraint, not a convention.** Both facts enforce their natural key,
  so accidental fan-out (double-counted approaches / duplicate snapshots) is impossible. This protects BI
  counts *and* the "one row = one training example" AI invariant simultaneously.
- **Time anchors on every fact/feature row** (`close_approach_date`, `snapshot_date`). *Why:* enables BI
  time-series, ML temporal splits/forecasting (UC-4), and leakage-safe train/test boundaries.
- **Surrogate keys flow end-to-end** (silver → AI feature id → `ml.prediction.snapshot_ref`), giving full
  lineage from a raw event to a model's score.
- **dbt is the single transformation contract for gold.** Both families are dbt models with tests, so BI
  metrics and ML features can never silently disagree about what the underlying numbers mean.

---

## 7. Known Limitations & Honest Caveats

- **`is_hazardous_label` is partly deterministic.** NASA's hazardous flag is largely a rule on absolute
  magnitude and minimum-orbit-intersection distance. A classifier on `ai_neo_features` will score very
  high partly by "memorizing" that rule. This is acknowledged in [ai_implementation.md](ai_implementation.md):
  treat UC-1 as an **MLOps/pipeline demonstration**, and prefer a derived, non-deterministic target for a
  genuine learning task. The *modeling* (flat labeled feature table) is correct either way.
- **Short local history limits time-aware models.** Limited real history constrains forecasting (UC-4) and
  per-satellite anomaly detection (UC-3); synthetic backfill is used to lengthen series. The grain choices
  already support these once more history exists.
- **No slowly-changing-dimension (SCD2) history yet.** Dimensions (`silver.neo`, `silver.satcat_satellite`)
  keep `first_seen_date` / `last_seen_date` but not full attribute-change history. Acceptable for current
  scope; an SCD2 upgrade is the natural extension if attribute-change tracking becomes a requirement.

---

## 8. Summary

- **One conformed silver core** (two dimensions + two facts, explicit grain, surrogate keys) is the single
  source of truth.
- **BI gold** = Kimball **star + aggregated marts** → chosen because every in-scope BI question is a
  slice/aggregate over events by a descriptive attribute or time; rejected 3NF/OBT/Data-Vault/cubes as
  over- or under-fit for the scale and access pattern.
- **AI gold** = **flat, atomic, labeled feature tables** → chosen because it is the native, signal-preserving,
  reproducible input shape for `scikit-learn`; rejected bronze-direct, BI-mart, normalized, and external
  feature-store approaches as skew-prone, wrong-grain, or over-engineered.
- The **fork is the point:** two purpose-built gold shapes, one governed silver foundation — each consumer
  gets the model that fits its access pattern without compromising the other.

---

## See Also

- [data_flow.md](data_flow.md) — end-to-end bronze → silver → gold movement
- [architecture_principles.md](architecture_principles.md) — medallion + warehouse strategy
- [ai_implementation.md](ai_implementation.md) — AI/ML workstream plan that consumes `gold.ai_*`
- [scope.md](scope.md) — personas and the BI questions this model answers
- [source_data.md](source_data.md) — the two sources behind the silver entities
