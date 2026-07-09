-- fails if a trip under 2 minutes covers more than 3 miles; these are exempt
-- from the speed check (duration truncation can inflate computed speed) but
-- are still implausible outright -- even a sustained 80mph for 2 minutes
-- only covers ~2.6 miles
select *
from {{ ref('stg_yellow_trips') }}
where trip_duration_minutes < 2
  and trip_distance > 3
