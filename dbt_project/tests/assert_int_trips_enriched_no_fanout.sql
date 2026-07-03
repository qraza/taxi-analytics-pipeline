-- fails if the zone left joins in int_trips_enriched inflate or drop rows
with source_count as (
    select count(*) as cnt from {{ ref('stg_yellow_trips') }}
),

enriched_count as (
    select count(*) as cnt from {{ ref('int_trips_enriched') }}
)

select *
from source_count s
join enriched_count e on s.cnt != e.cnt
