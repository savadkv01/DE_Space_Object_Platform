-- dbt/space_objects/models/gold/ai_neo_features.sql

{{ config(
    materialized="table"
) }}

select
    ca.approach_sk,
    ca.neo_id,
    ca.close_approach_date,
    ca.rel_velocity_km_s,
    ca.rel_velocity_km_h,
    ca.miss_distance_km,
    ca.miss_distance_lunar,
    ca.miss_distance_au,
    n.absolute_magnitude_h,
    case when n.is_potentially_hazardous_asteroid then 1 else 0 end as is_hazardous_label
from {{ ref('neo_close_approach') }} ca
join {{ ref('neo') }} n
  on ca.neo_id = n.neo_id
