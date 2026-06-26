-- dbt/space_objects/models/gold/neo_hazard_summary.sql

{{ config(
    materialized="table"
) }}

select
    ca.neo_id,
    max(n.name) as name,
    bool_or(n.is_potentially_hazardous_asteroid) as is_hazardous,
    count(*) as total_approaches,
    min(ca.close_approach_date) as first_approach_date,
    max(ca.close_approach_date) as last_approach_date,
    min(ca.miss_distance_km) as closest_approach_km
from {{ ref('neo_close_approach') }} ca
left join {{ ref('neo') }} n using (neo_id)
group by ca.neo_id
