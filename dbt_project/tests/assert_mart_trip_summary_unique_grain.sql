-- fails if (trip_date, pickup_location_id) is not unique in mart_trip_summary
select trip_date, pickup_location_id, count(*) as row_count
from {{ ref('mart_trip_summary') }}
group by 1, 2
having count(*) > 1
