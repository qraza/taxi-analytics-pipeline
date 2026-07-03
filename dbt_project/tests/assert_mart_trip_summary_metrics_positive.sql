-- every group is backed by at least one filtered, revenue-positive trip,
-- so these aggregates should never be zero or negative
select *
from {{ ref('mart_trip_summary') }}
where total_trips <= 0
   or total_revenue_usd <= 0
