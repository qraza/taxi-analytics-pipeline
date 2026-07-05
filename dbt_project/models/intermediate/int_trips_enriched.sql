with trips as (
    select * from {{ ref('stg_yellow_trips') }}
),

zones as (
    select * from {{ ref('stg_taxi_zones') }}
)

select
    -- keys
    t.pickup_location_id,
    t.dropoff_location_id,

    -- pickup zone enrichment
    pu.zone_name    as pickup_zone,
    pu.borough      as pickup_borough,

    -- dropoff zone enrichment
    dof.zone_name   as dropoff_zone,
    dof.borough     as dropoff_borough,

    -- time grains
    cast(t.pickup_at as date)               as trip_date,
    extract(hour from t.pickup_at)          as pickup_hour,
    dayname(t.pickup_at)                    as pickup_day_of_week,

    -- trip facts
    t.trip_distance,
    t.trip_duration_minutes,
    t.passenger_count,

    -- financial facts + derived business metrics
    t.fare_amount,
    t.tip_amount,
    t.tolls_amount,
    t.total_amount,
    round(t.tip_amount / nullif(t.fare_amount, 0), 4)                    as tip_pct,
    round(60 * t.trip_distance / nullif(t.trip_duration_minutes, 0), 2)  as avg_speed_mph,

    -- airport flag
    (pu.zone_name ilike '%Airport%' or dof.zone_name ilike '%Airport%') as is_airport_trip

from trips t
left join zones pu on t.pickup_location_id = pu.location_id
left join zones dof on t.dropoff_location_id = dof.location_id
