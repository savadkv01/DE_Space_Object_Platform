-- dbt/space_objects/models/gold/ai_satcat_features.sql

{{ config(
    materialized="table"
) }}

select
    o.orbit_snapshot_sk,
    o.norad_cat_id,
    o.snapshot_date,
    o.period_minutes,
    o.inclination_deg,
    o.apogee_km,
    o.perigee_km,
    s.object_type,
    s.owner
from {{ ref('satcat_orbit_snapshot') }} o
join {{ ref('satcat_satellite') }} s
  on o.norad_cat_id = s.norad_cat_id
