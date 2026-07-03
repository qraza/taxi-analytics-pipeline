-- edge case: trip_date is cast from a timestamp, so a timezone or
-- date-boundary regression could spill rows outside the source month
select *
from {{ ref('mart_trip_summary') }}
where trip_date < date '2024-01-01'
   or trip_date > date '2024-01-31'
