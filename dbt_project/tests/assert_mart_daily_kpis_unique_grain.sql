-- fails if trip_date is not unique in mart_daily_kpis
select trip_date, count(*) as row_count
from {{ ref('mart_daily_kpis') }}
group by 1
having count(*) > 1
