-- fails if total revenue in the mart drifts from int_trips_enriched by more
-- than a cent per group (small drift is expected from per-group rounding)
with mart_total as (
    select sum(total_revenue_usd) as amt, count(*) as n_groups
    from {{ ref('mart_trip_summary') }}
),

source_total as (
    select sum(total_amount) as amt from {{ ref('int_trips_enriched') }}
)

select *
from mart_total m
join source_total s on abs(m.amt - s.amt) > 0.01 * m.n_groups
