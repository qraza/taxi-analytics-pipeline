# NYC Taxi Dashboard

A Streamlit dashboard over the `dbt_project` marts.

## Launch

```bash
uv sync --group dev
export DBT_DB_PATH=$(pwd)/data/capstone.duckdb   # optional, defaults to data/capstone.duckdb
export ANTHROPIC_API_KEY=sk-ant-...              # optional, enables the AI tabs
streamlit run app/dashboard.py
```

## Tabs

- **Explorer** — filter `mart_trip_summary` by date/borough/top-N and ask Claude for a
  written analysis of the selection.
- **Executive Overview** — month-level KPIs, daily trend, top zones, and revenue by
  borough, from `mart_daily_kpis` and `mart_trip_summary`.
- **Operational Insights** — day-of-week x hour demand heatmap, airport vs
  non-airport split, and tip-percentage patterns, from `mart_hourly_patterns` and
  `mart_daily_kpis`.
- **AI Analyst** — free-text Q&A grounded in a compact summary of the current month's
  KPIs and top zones.

The AI tabs require `ANTHROPIC_API_KEY`; without it they show setup guidance instead
of erroring.
