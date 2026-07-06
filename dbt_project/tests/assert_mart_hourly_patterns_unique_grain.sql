-- fails if (pickup_day_of_week, pickup_hour) is not unique in mart_hourly_patterns
select pickup_day_of_week, pickup_hour, count(*) as row_count
from {{ ref('mart_hourly_patterns') }}
group by 1, 2
having count(*) > 1
