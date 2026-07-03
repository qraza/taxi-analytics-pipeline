-- fails if avg_speed_mph is negative or implausibly high for a taxi trip
select *
from {{ ref('int_trips_enriched') }}
where avg_speed_mph is not null
  and (avg_speed_mph < 0 or avg_speed_mph > 100)
