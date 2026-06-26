-- dbt/space_objects/models/silver/satcat_satellite.sql

{{ config(
    materialized="ephemeral"
) }}

select
    satellite_sk,
    norad_cat_id,
    object_id,
    object_name,
    object_type,
    owner,
    ops_status_code,
    launch_date,
    launch_site,
    decay_date,
    orbit_center,
    orbit_type,
    rcs,
    first_seen_date,
    last_seen_date
from {{ source('silver', 'satcat_satellite') }}
