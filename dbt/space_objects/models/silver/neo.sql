-- dbt/space_objects/models/silver/neo.sql

{{ config(
    materialized="ephemeral"
) }}

select
    neo_sk,
    neo_id,
    neo_reference_id,
    name,
    absolute_magnitude_h,
    estimated_diameter_km_min,
    estimated_diameter_km_max,
    is_potentially_hazardous_asteroid,
    is_sentry_object,
    nasa_jpl_url,
    first_seen_date,
    last_seen_date
from {{ source('silver', 'neo') }}
