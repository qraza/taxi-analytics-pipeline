-- fails if any trip has a negative tip percentage
select *
from {{ ref('int_trips_enriched') }}
where tip_pct < 0
