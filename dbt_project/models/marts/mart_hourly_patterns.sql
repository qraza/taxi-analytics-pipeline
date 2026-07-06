with trips as (
    select * from {{ ref('int_trips_enriched') }}
),

day_occurrences as (
    select
        pickup_day_of_week,
        count(distinct trip_date) as n_dates
    from trips
    group by 1
)

select
    t.pickup_day_of_week,
    t.pickup_hour,
    count(*)                                          as total_trips,
    round(count(*) / d.n_dates, 1)                    as avg_trips_per_day,
    round(avg(t.fare_amount), 2)                       as avg_fare_usd,
    round(avg(t.tip_pct), 4)                           as avg_tip_pct
from trips t
inner join day_occurrences d on t.pickup_day_of_week = d.pickup_day_of_week
group by 1, 2, d.n_dates
order by
    case t.pickup_day_of_week
        when 'Monday' then 1
        when 'Tuesday' then 2
        when 'Wednesday' then 3
        when 'Thursday' then 4
        when 'Friday' then 5
        when 'Saturday' then 6
        when 'Sunday' then 7
    end,
    t.pickup_hour
