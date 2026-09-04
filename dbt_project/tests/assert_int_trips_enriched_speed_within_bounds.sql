-- fails if avg_speed_mph is negative or implausibly high for a sustained taxi trip;
-- trips under 2 minutes are excluded because whole-minute duration truncation
-- can inflate their computed speed (e.g. a 1:59 trip truncates to 1 minute)
select *
from {{ ref('int_trips_enriched') }}
where avg_speed_mph is not null
  and trip_duration_minutes >= 2
  and (avg_speed_mph < 0 or avg_speed_mph > 80)
