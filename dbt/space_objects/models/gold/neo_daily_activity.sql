-- dbt/space_objects/models/gold/neo_daily_activity.sql

{{ config(
    materialized="table"
) }}

with base as (
    select
        ca.close_approach_date,
        ca.neo_id,
        n.name,
        n.is_potentially_hazardous_asteroid
    from {{ ref('neo_close_approach') }} ca
    join {{ ref('neo') }} n
      on ca.neo_id = n.neo_id
)

select
    close_approach_date,
    count(*)                                as total_approaches,
    count(distinct neo_id)                  as unique_objects,
    sum(case when is_potentially_hazardous_asteroid then 1 else 0 end)
                                            as hazardous_approaches
from base
group by close_approach_date
order by close_approach_date
