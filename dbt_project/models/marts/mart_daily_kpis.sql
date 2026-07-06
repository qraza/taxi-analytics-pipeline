with trips as (
    select * from {{ ref('int_trips_enriched') }}
)

select
    trip_date,
    count(*)                                                     as total_trips,
    round(sum(total_amount), 2)                                  as total_revenue_usd,
    round(avg(fare_amount), 2)                                   as avg_fare_usd,
    round(avg(trip_duration_minutes), 1)                         as avg_duration_minutes,
    round(avg(tip_pct), 4)                                       as avg_tip_pct,
    round(avg(case when is_airport_trip then 1 else 0 end), 4)   as airport_trip_share
from trips
group by 1
order by trip_date
