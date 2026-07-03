-- fails if the aggregation drops or double-counts trips vs int_trips_enriched
with mart_total as (
    select sum(total_trips) as cnt from {{ ref('mart_trip_summary') }}
),

source_total as (
    select count(*) as cnt from {{ ref('int_trips_enriched') }}
)

select *
from mart_total m
join source_total s on m.cnt != s.cnt
