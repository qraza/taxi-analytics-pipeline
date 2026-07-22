-- fails if (pickup_month, pickup_day_of_week, pickup_hour) is not unique in mart_hourly_patterns
select pickup_month, pickup_day_of_week, pickup_hour, count(*) as row_count
from {{ ref('mart_hourly_patterns') }}
group by 1, 2, 3
having count(*) > 1
