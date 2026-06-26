# AI/ML Implementation Plan – Space Objects Data Platform

> **Status:** Proposed (not yet implemented)
> **Audience:** Implementation agent / engineer picking up the AI/ML workstream.
> **Prerequisite reading:** [scope.md](scope.md), [architecture.md](architecture.md), [architecture_principles.md](architecture_principles.md), [data_flow.md](data_flow.md).

This document reviews the current platform, catalogs viable AI/ML use cases, and gives a
phased, file-by-file implementation plan that fits the existing conventions (Docker-only,
on-prem, PostgreSQL-as-warehouse, Airflow-orchestrated, dbt feature tables).

---

## 1. Current-State Assessment

### What already exists and is AI-ready

| Asset | Location | Relevance to AI |
|---|---|---|
| `gold.ai_neo_features` | [dbt/space_objects/models/gold/ai_neo_features.sql](../dbt/space_objects/models/gold/ai_neo_features.sql) | Per close-approach feature row **with label** `is_hazardous_label`. Ready-made supervised training set. |
| `gold.ai_satcat_features` | [dbt/space_objects/models/gold/ai_satcat_features.sql](../dbt/space_objects/models/gold/ai_satcat_features.sql) | Per orbit-snapshot features (period, inclination, apogee, perigee, object_type, owner). Ready for classification/clustering. |
| `gold.neo_daily_activity` | [dbt/space_objects/models/gold/neo_daily_activity.sql](../dbt/space_objects/models/gold/neo_daily_activity.sql) | Daily time series → forecasting input. |
| `silver.*` normalized tables | Spark-managed | Clean source for any feature engineering. |
| `meta.pipeline_run` / `meta.data_quality_run` | [infra/postgres/init.sql](../infra/postgres/init.sql) | Reusable run/DQ tracking pattern for ML jobs. |
| `services/common/*` | db_client, config_loader, logging_utils, metrics_utils | Reusable DB + config + logging plumbing. |
| Airflow + dbt + Spark | Containerized | Orchestration and (optional) distributed training/inference. |

### Gaps (what the AI workstream must add)

1. **No `ml` schema** — nowhere to persist predictions, model registry metadata, or evaluation metrics.
2. **No training/inference code** — no `services/ml/` package.
3. **No model artifact storage / experiment tracking** — no MLflow or equivalent.
4. **No ML orchestration** — no training or batch-scoring DAGs.
5. **No serving path** — no way to query a model for a single object.
6. **No drift / model-quality monitoring** — `meta` only tracks data pipelines today.

### Design constraints (inherited — do not violate)

- **No cloud services.** Everything runs in Docker on `space_net`.
- **PostgreSQL is the single warehouse.** Persist predictions/metrics there (new `ml` schema).
- **Laptop-scale (~16 GB RAM).** Prefer scikit-learn / lightweight models; avoid GPU/deep-learning unless local-CPU-friendly.
- **Reuse existing patterns:** `services/common` clients, `meta.pipeline_run` run tracking, Airflow DAGs volume-mounted, `init.sql` `CREATE ... IF NOT EXISTS`.
- **No `container_name:`**, port-remap conventions, `.env` for secrets.

---

## 2. AI/ML Use-Case Catalog

Prioritized by value-vs-effort and data availability. Phases in §4 implement them in this order.

| # | Use case | Type | Data source | Feasibility | Priority |
|---|---|---|---|---|---|
| UC-1 | **NEO hazard classification** — predict `is_potentially_hazardous` from orbital/approach features | Supervised binary classification | `gold.ai_neo_features` | High — labeled data already exists | **P0** |
| UC-2 | **Satellite orbit-regime classification** — predict LEO/MEO/GEO/HEO from orbital params | Supervised multiclass | `gold.ai_satcat_features` (+ derive label from apogee/perigee) | High | **P1** |
| UC-3 | **Orbital anomaly / decay detection** — flag satellites whose orbit snapshots deviate from their own history | Unsupervised (IsolationForest / z-score on deltas) | `silver.satcat_orbit_snapshot` time series | Medium — needs multi-snapshot history | **P1** |
| UC-4 | **NEO close-approach forecasting** — forecast daily close-approach counts | Time-series forecast | `gold.neo_daily_activity` | Medium — limited history locally; use synthetic backfill | **P2** |
| UC-5 | **Satellite clustering** — discover constellations / orbital families | Unsupervised clustering (KMeans/DBSCAN) | `gold.ai_satcat_features` | Medium | **P2** |
| UC-6 | **GenAI situational-awareness brief / NL-to-SQL** — daily natural-language hazard summary and/or text-to-SQL over gold layer using a **local** LLM (Ollama) | GenAI (optional) | gold layer + docs | Low-Medium — optional, needs local LLM container | **P3** |

**Recommendation:** Implement UC-1 fully end-to-end first (it exercises every new component:
schema, training, registry, batch inference, DQ, DAG, dashboard). UC-2/UC-3 then reuse the
same scaffolding. UC-4/UC-5/UC-6 are stretch goals.

---

## 3. Target Architecture Additions

```
                 gold.ai_neo_features / gold.ai_satcat_features  (feature store, dbt-managed)
                                   │
                                   ▼
   ┌──────────────────────────────────────────────────────────┐
   │  services/ml/  (new Python package, reuses services/common) │
   │   ├── training: load features → train → eval → register     │
   │   └── inference: load model → score → write ml.prediction   │
   └───────────────┬──────────────────────────┬─────────────────┘
                   │ artifacts + metrics       │ predictions
                   ▼                           ▼
        MLflow (Docker, optional)        ml.* schema (PostgreSQL)
        - experiment tracking            - ml.model_registry
        - model registry/artifacts       - ml.prediction
        (file/sqlite backend, local)     - ml.model_metric
                   │                           │
                   ▼                           ▼
        Airflow: ml_train_dag          Airflow: ml_inference_dag
        (weekly retrain)               (daily score, after dbt_gold_dag)
                   │                           │
                   ▼                           ▼
        FastAPI ml-serving (Docker, optional)  Grafana panels on ml.* tables
        - /predict/neo  /predict/satcat
```

### Component decisions

| Concern | Choice | Rationale |
|---|---|---|
| ML framework | **scikit-learn** (+ optional `xgboost` CPU) | Laptop-scale, no GPU, mature, easy to serialize. |
| Forecasting (UC-4) | `statsmodels` (SARIMAX) or `prophet` (optional) | Lightweight, CPU-friendly. |
| Experiment tracking / registry | **MLflow** with local file/sqlite backend, artifacts on a Docker volume | On-prem, no cloud; doubles as model registry. *Optional* — can start with `ml.model_registry` table + artifacts on a volume only. |
| Prediction storage | New **`ml`** schema in PostgreSQL | Single-warehouse rule; consumable by Grafana/dbt. |
| Serving | **FastAPI** container (optional, P2) | Real-time single-object scoring; same `space_net`. |
| GenAI (UC-6) | **Ollama** container + small local model (e.g. `llama3.2:3b`) | On-prem, no cloud LLM calls. Optional. |
| Orchestration | Airflow DAGs (`ml_train_dag`, `ml_inference_dag`) | Consistent with existing pipeline. |
| Run tracking | Reuse `meta.pipeline_run` + `meta.data_quality_run` | ML jobs are pipelines too; keep one observability surface. |

---

## 4. Phased Implementation Plan

Each phase lists **files to create/modify**, **acceptance criteria**, and **commands**.
Follow existing conventions: env vars from `.env`, `services.common` imports, Spark/airflow
containers already mount the repo.

### Phase 0 — Foundations (schema, package, deps)

**4.0.1 Add `ml` schema + tables.** Append to [infra/postgres/init.sql](../infra/postgres/init.sql)
(use `CREATE ... IF NOT EXISTS`; keep idempotent). Also provide a standalone migration file
`infra/postgres/migrations/001_ml_schema.sql` so it can be applied to a running DB without
recreating the warehouse.

```sql
CREATE SCHEMA IF NOT EXISTS ml;

-- One row per trained model version
CREATE TABLE IF NOT EXISTS ml.model_registry (
  model_id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  model_name      text NOT NULL,            -- 'neo_hazard_classifier'
  model_version   integer NOT NULL,
  algorithm       text NOT NULL,            -- 'random_forest'
  feature_set     text NOT NULL,            -- 'gold.ai_neo_features'
  artifact_uri    text NOT NULL,            -- volume path or mlflow uri
  trained_at      timestamptz NOT NULL DEFAULT now(),
  training_run_id uuid REFERENCES meta.pipeline_run(run_id),
  is_active       boolean NOT NULL DEFAULT false,
  params          jsonb,
  UNIQUE (model_name, model_version)
);

-- Evaluation metrics per model version
CREATE TABLE IF NOT EXISTS ml.model_metric (
  metric_id    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  model_id     uuid NOT NULL REFERENCES ml.model_registry(model_id),
  metric_name  text NOT NULL,               -- 'roc_auc', 'f1', 'accuracy'
  metric_value double precision NOT NULL,
  dataset_split text NOT NULL,              -- 'train','test','holdout'
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Batch inference output (generic across models)
CREATE TABLE IF NOT EXISTS ml.prediction (
  prediction_id   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  model_id        uuid NOT NULL REFERENCES ml.model_registry(model_id),
  entity_type     text NOT NULL,            -- 'neo' | 'satellite'
  entity_key      text NOT NULL,            -- neo_id or norad_cat_id
  snapshot_ref    text,                     -- approach_sk / orbit_snapshot_sk / date
  predicted_label text,
  predicted_score double precision,         -- probability / anomaly score
  inference_run_id uuid REFERENCES meta.pipeline_run(run_id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ml_prediction_entity
  ON ml.prediction (entity_type, entity_key);
```

**4.0.2 Create the `services/ml/` package.**

```
services/ml/
  __init__.py
  config.py            # MLConfig: model dir, registry settings, feature SQL
  feature_loader.py    # load gold.ai_* into pandas via DbClient
  registry.py          # save/load artifacts + write ml.model_registry / ml.model_metric
  run_tracker.py       # thin wrapper around DbClient.create/update_pipeline_run + DQ rows
  training/
    __init__.py
    train_neo_hazard.py
  inference/
    __init__.py
    score_neo_hazard.py
```

- **Reuse** `services.common.db_client.DbClient`, `services.common.config_loader`, and
  `services.common.logging_utils` (match the structured log format).
- `feature_loader.py` should `SELECT * FROM gold.ai_neo_features` using a read-only query and
  return a pandas DataFrame.
- `registry.py` serializes models with `joblib` to a mounted volume path
  (`/opt/ml/artifacts/<model_name>/<version>/model.joblib`) and inserts the `ml.model_registry`
  row, flipping `is_active=false` on prior versions and `true` on the new one.

**4.0.3 Dependencies + container.** Create `infra/ml/Dockerfile` and `infra/ml/requirements.txt`
mirroring `infra/ingestion/`:

```
# infra/ml/requirements.txt
scikit-learn==1.5.*
pandas==2.2.*
numpy==1.26.*
joblib==1.4.*
psycopg2-binary==2.9.*
sqlalchemy==2.0.*       # optional, for read_sql convenience
mlflow==2.16.*          # optional (Phase 0b)
```

Add an `ml` build-only base service to `docker-compose.yml` mirroring the `ingestion:` pattern
(build context `.`, dockerfile `./infra/ml/Dockerfile`, image `space-objects-ml`, `env_file: .env`,
network `space_net`, `depends_on: postgres`). Add a named volume `ml_artifacts:` mounted at
`/opt/ml/artifacts`. **Do not** set `container_name:`.

> **Note:** The Airflow image can also run training if `scikit-learn` is added to
> [infra/airflow/requirements.txt](../infra/airflow/requirements.txt). Decide one of:
> (a) DAGs `docker run` the `space-objects-ml` image (cleaner isolation), or
> (b) DAGs import `services.ml` directly inside the Airflow container (simpler, fewer moving parts).
> **Recommended: (b)** for parity with how dbt/Spark already run inside Airflow.

**Acceptance (Phase 0):**
- `ml` schema + 3 tables exist (`\dt ml.*` shows them).
- `python -c "import services.ml"` succeeds inside the ML/Airflow image.
- `ml_artifacts` volume is created.

---

### Phase 0b — MLflow tracking (optional but recommended)

Add an `mlflow` service to `docker-compose.yml`:

```yaml
  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.16.2
    command: >
      mlflow server --host 0.0.0.0 --port 5000
      --backend-store-uri sqlite:////mlflow/mlflow.db
      --artifacts-destination /mlflow/artifacts
    ports:
      - "5500:5000"            # host:container, avoid common 5000 conflicts
    volumes:
      - mlflow_data:/mlflow
    networks:
      - space_net
```

- Set `MLFLOW_TRACKING_URI=http://mlflow:5000` in `.env`.
- `registry.py` logs params/metrics/artifacts to MLflow **in addition to** the `ml.*` tables
  (Postgres remains the canonical store for serving/dashboards).

**Acceptance:** MLflow UI reachable at `http://localhost:5500`; a test run appears.

---

### Phase 1 — UC-1: NEO Hazard Classification (P0, end-to-end)

This is the reference implementation; later models copy its structure.

**Files:**
- `services/ml/training/train_neo_hazard.py`
- `services/ml/inference/score_neo_hazard.py`
- `airflow/dags/ml_train_dag.py`
- `airflow/dags/ml_inference_dag.py`

**Training (`train_neo_hazard.py`):**
1. `run_id = DbClient.create_pipeline_run("ml_train_neo_hazard", triggered_by=...)`.
2. Load `gold.ai_neo_features` → DataFrame.
3. Features: `rel_velocity_km_s, miss_distance_km, miss_distance_lunar, absolute_magnitude_h`
   (drop identifiers/leaky columns). Label: `is_hazardous_label`.
4. `train_test_split(stratify=label, random_state=42)`.
5. Train `RandomForestClassifier` (start simple; `class_weight="balanced"` — hazardous is the minority class).
6. Evaluate: `roc_auc`, `f1`, `accuracy`, `precision`, `recall` on the test split.
7. `registry.save_model(...)` → writes artifact, `ml.model_registry` (new version, `is_active=true`),
   and one `ml.model_metric` row per metric. Optionally log to MLflow.
8. **DQ gate:** write a `meta.data_quality_run` row — e.g. fail the job if `roc_auc < 0.70`
   (configurable threshold) so a bad model never becomes active.
9. `DbClient.update_pipeline_run(run_id, "success", records_processed=n_rows)`.
10. Wrap in try/except → on error `update_pipeline_run(run_id, "failed", error_message=...)`.

> **Important caveat:** NASA's `is_potentially_hazardous_asteroid` is partly a deterministic
> function of absolute magnitude (≈H ≤ 22) and minimum-orbit-intersection distance. The model will
> likely score very high and partly "memorize" that rule. Document this honestly in the model card
> (`docs/`), and consider it a **pipeline/MLOps demonstration** rather than a novel predictor.
> For a more genuine learning task, predict a derived target such as "close approach within
> N lunar distances in the next window" using only pre-approach features.

**Inference (`score_neo_hazard.py`):**
1. `create_pipeline_run("ml_inference_neo_hazard", ...)`.
2. Load active model from `ml.model_registry` (`is_active=true`, latest version) via `registry.load_active("neo_hazard_classifier")`.
3. Load scoring rows from `gold.ai_neo_features` (all rows, or only those without a current prediction).
4. Predict label + probability.
5. Bulk insert into `ml.prediction` (`entity_type='neo'`, `entity_key=neo_id`, `snapshot_ref=approach_sk`,
   `predicted_score=proba`) using `DbClient.executemany`.
6. Update pipeline run.

**Airflow DAGs:**
- `ml_train_dag` — `schedule="@weekly"`, `catchup=False`, tags `["ml","training"]`. Single task that
  runs the trainer (PythonOperator importing `services.ml.training.train_neo_hazard:main`, or
  BashOperator `python -m services.ml.training.train_neo_hazard`).
- `ml_inference_dag` — `schedule="@daily"`, runs **after** `dbt_gold_dag` (feature tables must be
  fresh). Use an `ExternalTaskSensor` on `dbt_gold_dag` or chain via dataset/trigger. Tag `["ml","inference"]`.

**Grafana:** add a panel/query on `ml.prediction` (e.g. count of predicted-hazardous NEOs per day,
and a table joining `ml.prediction` → `gold.ai_neo_features` for top-risk upcoming approaches).

**Acceptance (Phase 1):**
- `python -m services.ml.training.train_neo_hazard` produces a `ml.model_registry` row with
  `is_active=true`, ≥1 `ml.model_metric` rows, and a `joblib` artifact on the volume.
- `python -m services.ml.inference.score_neo_hazard` writes N `ml.prediction` rows (N = feature rows).
- Both jobs create `meta.pipeline_run` rows with `status='success'`.
- `ml_train_dag` and `ml_inference_dag` parse and run green in Airflow.
- A model card markdown exists at `docs/model_card_neo_hazard.md` (metrics, features, caveats).

---

### Phase 2 — UC-2 & UC-3 (reuse scaffolding)

**UC-2 Orbit-regime classifier:**
- Derive the label in dbt: extend `ai_satcat_features` (or a new `ai_satcat_features_labeled` model)
  with `orbit_regime` from apogee/perigee/period:
  - LEO: apogee < 2,000 km; MEO: 2,000–35,000 km; GEO: ~35,786 km & inclination ≈ 0 & period ≈ 1436 min;
    HEO: high eccentricity (apogee ≫ perigee). Encode rules in SQL.
- `services/ml/training/train_orbit_regime.py` + `inference/score_orbit_regime.py` — copy UC-1 shape,
  multiclass `RandomForestClassifier`, metrics `accuracy`/`macro_f1`.
- Add tasks to `ml_train_dag` / `ml_inference_dag`.

**UC-3 Orbital anomaly detection (unsupervised):**
- Feature-engineer per-satellite snapshot deltas (period/apogee/perigee change vs previous snapshot)
  from `silver.satcat_orbit_snapshot` ordered by `snapshot_date`.
- Train `IsolationForest` per cohort (or global) → anomaly score.
- Write to `ml.prediction` with `entity_type='satellite'`, `predicted_label='anomaly'|'normal'`,
  `predicted_score=anomaly_score`.
- Useful Grafana panel: top-N anomalous satellites by score.

**Acceptance (Phase 2):** both models registered + scoring into `ml.prediction`; DAG tasks green.

---

### Phase 3 — UC-4 / UC-5 / UC-6 (stretch)

- **UC-4 Forecast:** SARIMAX/Prophet on `gold.neo_daily_activity`; write forecasts to a
  `ml.forecast` table (date, horizon, yhat, yhat_lower, yhat_upper). Note: local history is short —
  use synthetic backfill (`docker compose --profile synthetic ...`) to lengthen the series.
- **UC-5 Clustering:** KMeans/DBSCAN on `gold.ai_satcat_features`; persist cluster labels to
  `ml.prediction` (`predicted_label=cluster_id`). Add silhouette score to `ml.model_metric`.
- **UC-6 GenAI (optional):** add `ollama` service (Docker) + small model; build a
  `services/ml/genai/` module that (a) generates a daily NL situational brief from gold tables, or
  (b) does guarded text-to-SQL over the gold schema (whitelist tables, read-only DB role, validate
  generated SQL before execution). **Never** expose write access to the LLM path.

---

## 5. Conventions & Guardrails for the Implementing Agent

- **Imports:** always go through `services.common` (`DbClient`, `config_loader`, `logging_utils`).
  Do not re-implement DB connections.
- **Run tracking:** every training/inference entrypoint must bracket work with
  `create_pipeline_run` / `update_pipeline_run` and write DQ rows for quality gates.
- **Idempotency:** inference should be safe to re-run (e.g. delete-and-reinsert per
  `inference_run_id`, or upsert on natural key). Training bumps `model_version` and toggles `is_active`.
- **Reproducibility:** fix `random_state=42`; log params to `ml.model_registry.params` (+ MLflow).
- **Secrets:** API keys / URIs via `.env` only; never log them.
- **No cloud, no GPU.** Keep models CPU/laptop-friendly.
- **Docker rules:** no `container_name:`; remap host ports to avoid conflicts; one `space_net`.
- **dbt for features only.** Feature engineering that can be SQL belongs in dbt gold models; Python
  ML code should consume features, not re-derive them.
- **Honesty in model cards.** Document data leakage / deterministic-label caveats (esp. UC-1).

---

## 6. Reference Commands

```bash
# Apply ml schema migration to a running warehouse
docker exec -i space_object_platform-postgres-1 \
  psql -U space_user -d space_warehouse < infra/postgres/migrations/001_ml_schema.sql

# Train (inside Airflow container, parity with dbt/Spark execution)
docker exec space_object_platform-airflow-scheduler-1 \
  python -m services.ml.training.train_neo_hazard

# Batch score
docker exec space_object_platform-airflow-scheduler-1 \
  python -m services.ml.inference.score_neo_hazard

# Inspect results
docker exec space_object_platform-postgres-1 psql -U space_user -d space_warehouse \
  -c "SELECT model_name, model_version, is_active FROM ml.model_registry ORDER BY trained_at DESC;"
docker exec space_object_platform-postgres-1 psql -U space_user -d space_warehouse \
  -c "SELECT metric_name, metric_value, dataset_split FROM ml.model_metric ORDER BY created_at DESC;"
docker exec space_object_platform-postgres-1 psql -U space_user -d space_warehouse \
  -c "SELECT entity_type, COUNT(*) FROM ml.prediction GROUP BY 1;"

# (Optional) MLflow UI
# http://localhost:5500
```

---

## 7. Implementation Checklist (for the pickup agent)

- [ ] **P0** `ml` schema + `migrations/001_ml_schema.sql`
- [ ] **P0** `services/ml/` package scaffold (config, feature_loader, registry, run_tracker)
- [ ] **P0** `infra/ml/Dockerfile` + `requirements.txt`; compose `ml` service + `ml_artifacts` volume
- [ ] **P0b** (optional) MLflow service + `MLFLOW_TRACKING_URI`
- [ ] **P1** `train_neo_hazard.py` + `score_neo_hazard.py`
- [ ] **P1** `ml_train_dag.py` + `ml_inference_dag.py` (inference after `dbt_gold_dag`)
- [ ] **P1** `docs/model_card_neo_hazard.md`
- [ ] **P1** Grafana panel on `ml.prediction`
- [ ] **P2** UC-2 orbit-regime (dbt label + train/score) and UC-3 anomaly detection
- [ ] **P3** UC-4 forecast / UC-5 clustering / UC-6 GenAI (stretch)
- [ ] Update [architecture.md](architecture.md) + [data_flow.md](data_flow.md) with the ML layer
- [ ] Update repo memory with new schema, DAGs, and run commands
