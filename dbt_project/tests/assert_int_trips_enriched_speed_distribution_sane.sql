-- fails if the median trip speed is implausibly low. Row-level bounds catch
-- outlier records; this catches *systemic* errors that shift every row at
-- once — e.g. a units mistake dropping the minutes->hours factor divides all
-- speeds by 60, sliding the whole distribution under any sane median while
-- individual rows still look "possible". Real NYC median is ~10 mph; even
-- gridlock-heavy samples sit well above 3.
with stats as (
    select median(avg_speed_mph) as median_speed_mph
    from {{ ref('int_trips_enriched') }}
    where avg_speed_mph is not null
      and trip_duration_minutes >= 2
)
select *
from stats
where median_speed_mph < 3
