-- regression guard: every row must satisfy stg_yellow_trips' intended filters,
-- so a future edit to its WHERE clause can't silently let bad rows through
select *
from {{ ref('stg_yellow_trips') }}
where not (
    trip_distance > 0
    and trip_distance < 100
    and fare_amount > 0
    and total_amount > 0
    and passenger_count > 0
    and trip_duration_minutes >= 0
    and pickup_at >= '2024-01-01'
    and pickup_at < '2024-02-01'
)
