-- dbt/space_objects/models/silver/neo_close_approach.sql

{{ config(
    materialized="ephemeral"
) }}

select
    approach_sk,
    neo_sk,
    neo_id,
    close_approach_date,
    close_approach_date_full,
    epoch_date_close_approach,
    orbiting_body,
    rel_velocity_km_s,
    rel_velocity_km_h,
    rel_velocity_mi_h,
    miss_distance_km,
    miss_distance_lunar,
    miss_distance_au,
    miss_distance_miles,
    ingestion_timestamp,
    source_run_id
from {{ source('silver', 'neo_close_approach') }}
