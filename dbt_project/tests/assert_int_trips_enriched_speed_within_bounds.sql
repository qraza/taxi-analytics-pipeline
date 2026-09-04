-- fails if avg_speed_mph is negative, implausibly high, or implausibly low for
-- a sustained taxi trip; trips under 2 minutes are excluded because whole-minute
-- duration truncation can inflate their computed speed (e.g. a 1:59 trip
-- truncates to 1 minute).
-- The lower bound (1 mph) exists because a units error can shrink every speed
-- uniformly (e.g. dropping the minutes->hours factor divides all speeds by 60):
-- an upper bound alone cannot catch that class of bug.
select *
from {{ ref('int_trips_enriched') }}
where avg_speed_mph is not null
  and trip_duration_minutes >= 2
  and (avg_speed_mph < 1 or avg_speed_mph > 80)
