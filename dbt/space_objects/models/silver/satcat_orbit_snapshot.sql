-- dbt/space_objects/models/silver/satcat_orbit_snapshot.sql

{{ config(
    materialized="ephemeral"
) }}

select
    orbit_snapshot_sk,
    satellite_sk,
    norad_cat_id,
    snapshot_date,
    period_minutes,
    inclination_deg,
    apogee_km,
    perigee_km,
    ecc,
    mean_motion_rev_per_day,
    ingestion_timestamp,
    source_group,
    source_run_id
from {{ source('silver', 'satcat_orbit_snapshot') }}
