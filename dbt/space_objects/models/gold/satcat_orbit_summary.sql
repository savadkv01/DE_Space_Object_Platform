-- dbt/space_objects/models/gold/satcat_orbit_summary.sql

{{ config(
    materialized="table"
) }}

with joined as (
    select
        s.norad_cat_id,
        s.object_name,
        s.object_type,
        s.owner,
        o.snapshot_date,
        o.period_minutes,
        o.inclination_deg,
        o.apogee_km,
        o.perigee_km
    from {{ ref('satcat_satellite') }} s
    join {{ ref('satcat_orbit_snapshot') }} o
      on s.norad_cat_id = o.norad_cat_id
)

select
    norad_cat_id,
    max(object_name) as object_name,
    max(object_type) as object_type,
    max(owner) as owner,
    count(*) as snapshot_count,
    min(snapshot_date) as first_snapshot_date,
    max(snapshot_date) as last_snapshot_date,
    avg(period_minutes) as avg_period_minutes,
    avg(inclination_deg) as avg_inclination_deg,
    avg(apogee_km) as avg_apogee_km,
    avg(perigee_km) as avg_perigee_km
from joined
group by norad_cat_id
