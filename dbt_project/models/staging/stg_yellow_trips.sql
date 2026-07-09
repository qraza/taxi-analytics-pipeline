with source as (
    select * from {{ source('nyc_tlc', 'yellow_trips') }}
),

cleaned as (
    select
        -- identifiers
        VendorID                                        as vendor_id,
        PULocationID                                    as pickup_location_id,
        DOLocationID                                    as dropoff_location_id,

        -- timestamps
        tpep_pickup_datetime                            as pickup_at,
        tpep_dropoff_datetime                           as dropoff_at,

        -- derived
        datediff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) as trip_duration_minutes,

        -- trip details
        passenger_count,
        trip_distance,
        payment_type,

        -- financials
        fare_amount,
        tip_amount,
        tolls_amount,
        total_amount

    from source
    where
        tpep_pickup_datetime >= '2024-01-01'
        and tpep_pickup_datetime < '2024-02-01'
        and trip_distance > 0
        and trip_distance < 100
        and fare_amount > 0
        and total_amount > 0
        and passenger_count > 0
        and datediff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) >= 0
)

select *
from cleaned
where
    -- drop implausible-speed trips (bad meter/GPS records); trips under 2
    -- minutes are exempt from the speed check since whole-minute duration
    -- truncation can inflate their computed speed, but they're still capped
    -- at 3 miles -- even a sustained 80mph for 2 minutes covers ~2.6 miles
    (trip_duration_minutes < 2 and trip_distance <= 3)
    or (trip_duration_minutes >= 2 and (60 * trip_distance / trip_duration_minutes) <= 80)
