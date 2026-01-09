-- ==============================
-- Schema setup
-- ==============================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS dq;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================
-- META TABLES
-- ==============================

-- Tracks each pipeline/job run (batch ingestion, Spark jobs, dbt, etc.)
CREATE TABLE IF NOT EXISTS meta.pipeline_run (
  run_id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  pipeline_name     text NOT NULL,        -- e.g. 'nasa_neo_batch_ingestion'
  triggered_by      text,                 -- 'airflow', 'manual', etc.
  dag_id            text,
  task_id           text,
  start_time        timestamptz NOT NULL DEFAULT now(),
  end_time          timestamptz,
  status            text NOT NULL,        -- 'running', 'success', 'failed'
  records_processed bigint,
  error_message     text
);

-- Tracks data quality check results per pipeline run
CREATE TABLE IF NOT EXISTS meta.data_quality_run (
  dq_run_id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_id            uuid REFERENCES meta.pipeline_run(run_id),
  check_name        text NOT NULL,        -- e.g. 'neo_non_null_id'
  status            text NOT NULL,        -- 'pass', 'fail'
  total_records     bigint,
  failed_records    bigint,
  details           jsonb,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- ==============================
-- BRONZE TABLES
-- ==============================

-- 1) NASA NEO feed raw: one row per API feed response
CREATE TABLE IF NOT EXISTS bronze.nasa_neo_feed_raw (
  id                  bigserial PRIMARY KEY,
  ingestion_timestamp timestamptz NOT NULL DEFAULT now(),
  start_date          date NOT NULL,
  end_date            date NOT NULL,
  element_count       integer,
  raw_payload         jsonb NOT NULL
);

-- 2) NASA NEO event raw: one row per close-approach event
CREATE TABLE IF NOT EXISTS bronze.nasa_neo_event_raw (
  event_id                       bigserial PRIMARY KEY,
  ingestion_timestamp            timestamptz NOT NULL DEFAULT now(),
  feed_start_date                date NOT NULL,
  feed_end_date                  date NOT NULL,

  neo_id                         text NOT NULL,
  neo_reference_id               text,
  neo_name                       text,
  is_potentially_hazardous_asteroid boolean,
  absolute_magnitude_h           numeric,

  estimated_diameter             jsonb,     -- full nested diameter object

  close_approach_date            date NOT NULL,
  close_approach_date_full       text,
  epoch_date_close_approach      bigint,
  relative_velocity              jsonb,     -- nested velocities
  miss_distance                  jsonb,     -- nested distances
  orbiting_body                  text,

  raw_neo                        jsonb      -- full original NEO record
);

-- Natural key for deduplication (NEO + datetime + body)
CREATE UNIQUE INDEX IF NOT EXISTS ux_nasa_neo_event_raw_nk
ON bronze.nasa_neo_event_raw (neo_id, close_approach_date_full, orbiting_body);


-- 3) CelesTrak SATCAT raw: one row per CSV record
CREATE TABLE IF NOT EXISTS bronze.celestrak_satcat_raw (
  id                  bigserial PRIMARY KEY,
  ingestion_timestamp timestamptz NOT NULL DEFAULT now(),
  snapshot_group      text NOT NULL,      -- 'active', 'all', etc.
  snapshot_date       date NOT NULL,
  raw_csv_row         text NOT NULL,
  parsed_record       jsonb               -- optional JSON of parsed fields
);

-- 4) CelesTrak TLE raw: one row per 3-line TLE block
CREATE TABLE IF NOT EXISTS bronze.celestrak_tle_raw (
  id                  bigserial PRIMARY KEY,
  ingestion_timestamp timestamptz NOT NULL DEFAULT now(),
  snapshot_group      text NOT NULL,
  snapshot_date       date NOT NULL,
  norad_cat_id        integer,
  line0               text NOT NULL,      -- object name
  line1               text NOT NULL,
  line2               text NOT NULL
);

-- ==============================
-- SILVER TABLES
-- ==============================

-- 1) NEO dimension
CREATE TABLE IF NOT EXISTS silver.neo (
  neo_sk                    bigserial PRIMARY KEY, -- surrogate key
  neo_id                    text NOT NULL,         -- NASA id
  neo_reference_id          text,
  name                      text,
  absolute_magnitude_h      numeric,
  estimated_diameter_km_min numeric,
  estimated_diameter_km_max numeric,
  is_potentially_hazardous_asteroid boolean NOT NULL,
  is_sentry_object          boolean,
  nasa_jpl_url              text,
  first_seen_date           date,
  last_seen_date            date,

  CONSTRAINT ux_silver_neo_id UNIQUE (neo_id)
);

-- 2) NEO close-approach fact
CREATE TABLE IF NOT EXISTS silver.neo_close_approach (
  approach_sk                 bigserial PRIMARY KEY,
  neo_sk                      bigint NOT NULL REFERENCES silver.neo(neo_sk),
  neo_id                      text NOT NULL,

  close_approach_date         date NOT NULL,
  close_approach_date_full    text,
  epoch_date_close_approach   bigint,
  orbiting_body               text,

  rel_velocity_km_s           numeric,
  rel_velocity_km_h           numeric,
  rel_velocity_mi_h           numeric,

  miss_distance_km            numeric,
  miss_distance_lunar         numeric,
  miss_distance_au            numeric,
  miss_distance_miles         numeric,

  ingestion_timestamp         timestamptz NOT NULL DEFAULT now(),
  source_run_id               uuid,        -- link to meta.pipeline_run

  CONSTRAINT ux_silver_neo_close_approach_nk
  UNIQUE (neo_id, close_approach_date_full, orbiting_body)
);

CREATE INDEX IF NOT EXISTS idx_silver_neo_close_approach_date
ON silver.neo_close_approach (close_approach_date);

CREATE INDEX IF NOT EXISTS idx_silver_neo_close_approach_neo_id
ON silver.neo_close_approach (neo_id);


-- 3) SATCAT satellite dimension
CREATE TABLE IF NOT EXISTS silver.satcat_satellite (
  satellite_sk           bigserial PRIMARY KEY,
  norad_cat_id           integer NOT NULL,
  object_id              text,
  object_name            text NOT NULL,
  object_type            text,         -- 'PAY', 'DEB', etc.
  owner                  text,
  ops_status_code        text,
  launch_date            date,
  launch_site            text,
  decay_date             date,
  orbit_center           text,
  orbit_type             text,
  rcs                    numeric,

  first_seen_date        date,
  last_seen_date         date,

  CONSTRAINT ux_silver_satellite_norad UNIQUE (norad_cat_id)
);

-- 4) SATCAT orbit snapshot fact
CREATE TABLE IF NOT EXISTS silver.satcat_orbit_snapshot (
  orbit_snapshot_sk      bigserial PRIMARY KEY,
  satellite_sk           bigint NOT NULL REFERENCES silver.satcat_satellite(satellite_sk),
  norad_cat_id           integer NOT NULL,
  snapshot_date          date NOT NULL,

  period_minutes         numeric,
  inclination_deg        numeric,
  apogee_km              numeric,
  perigee_km             numeric,

  ecc                    numeric,      -- optional, from TLE parsing
  mean_motion_rev_per_day numeric,

  ingestion_timestamp    timestamptz NOT NULL DEFAULT now(),
  source_group           text,         -- 'active', 'all', etc.
  source_run_id          uuid,

  CONSTRAINT ux_silver_satcat_orbit_nk
  UNIQUE (norad_cat_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_silver_orbit_snapshot_date
ON silver.satcat_orbit_snapshot (snapshot_date);

CREATE INDEX IF NOT EXISTS idx_silver_orbit_snapshot_norad
ON silver.satcat_orbit_snapshot (norad_cat_id);
