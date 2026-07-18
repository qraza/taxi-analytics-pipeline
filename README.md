# taxi-analytics-pipeline

NYC Yellow Taxi trip data, from raw parquet to a tested dbt/DuckDB warehouse to three consumption
interfaces: a CLI, a Streamlit dashboard, and an automated PowerPoint deck.

[![CI](https://github.com/qraza/taxi-analytics-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/qraza/taxi-analytics-pipeline/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What this is

A portfolio project built to demonstrate a full analytics engineering stack end to end, not just
one layer of it. NYC TLC's public Yellow Taxi trip records are loaded into DuckDB, modelled through
a three-layer dbt project (staging → intermediate → marts), and covered by 71 dbt tests and 14
pytest tests that run in CI on every push. The marts are then consumed three ways: a Rich-formatted
CLI for quick lookups, a multi-tab Streamlit dashboard for interactive exploration, and a
`reporting/` module that builds a monthly board-pack PowerPoint deck — shared by both the CLI and
the dashboard so there's one chart-building codepath, not three. An optional LLM layer (Claude, via
the Anthropic API) sits on top of all three interfaces for natural-language analysis.

## Architecture

```
data/yellow_tripdata_2024-01.parquet ─┐
data/taxi_zone_lookup.csv ────────────┤
                                       ▼
                             scripts/load_raw.py
                                       │
                                       ▼
                          data/capstone.duckdb (nyc_tlc schema)
                                       │
                                       ▼
                              dbt_project/models
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                    ▼
              staging (view)   intermediate (ephemeral)   marts (table)
           stg_yellow_trips    int_trips_enriched      mart_trip_summary
           stg_taxi_zones                              mart_daily_kpis
                                                         mart_hourly_patterns
                                       │
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                    ▼
              cli/main.py      app/dashboard.py     reporting/deck_builder.py
           (summary, analyse,   (Streamlit,           (build_deck(), called by
            report commands)    4 tabs)                cli/main.py and the
                    │                  │                dashboard's export button)
                    └────────┬─────────┘                       │
                             ▼                                 │
                        cli/llm.py  ◄────────────────────────────┘
                   (Claude via Anthropic API —
                    optional, requires ANTHROPIC_API_KEY)
```

`reporting/figures.py` holds the plotly figure builders shared by the dashboard and the deck, so
both stay visually consistent.

## Stack

| Component        | Tool                | Why                                                        |
|-------------------|---------------------|-------------------------------------------------------------|
| Warehouse         | DuckDB               | Columnar OLAP engine, zero infrastructure, single file      |
| Transformation    | dbt-core + dbt-duckdb | Layered SQL models, built-in testing, lineage               |
| CLI               | Click + Rich          | Declarative commands, formatted terminal tables              |
| Dashboard         | Streamlit             | Fast interactive UI without a frontend build step             |
| Charts            | Plotly                | One figure library shared by the dashboard and the deck      |
| Deck export       | python-pptx + Kaleido | Programmatic PowerPoint generation from the same marts       |
| LLM layer         | Anthropic API (httpx) | Natural-language analysis over the mart data, opt-in         |
| Packaging         | uv                    | Fast, lockfile-based dependency management                    |
| Lint              | Ruff                  | Single fast linter, no separate formatter config              |
| Tests             | pytest + dbt tests    | Application logic and data quality tested separately          |
| CI                | GitHub Actions        | Runs lint, dbt build, and pytest on every push, no cloud creds |

## Quickstart

### Option A — local (uv)

```bash
git clone https://github.com/qraza/taxi-analytics-pipeline.git
cd taxi-analytics-pipeline
uv sync --group dev

mkdir -p data
wget -P data https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet
wget -P data https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv

source .venv/bin/activate
export DBT_DB_PATH="$(pwd)/data/capstone.duckdb"
python scripts/load_raw.py
dbt build --project-dir dbt_project --profiles-dir .ci
```

`--profiles-dir .ci` points dbt at the profile checked into the repo (`.ci/profiles.yml`), which
just reads the DuckDB path from `DBT_DB_PATH`. It works the same locally as it does in CI — no need
to hand-write a `~/.dbt/profiles.yml`.

### Option B — Docker

The image installs the whole project (`cli/`, `dbt_project/`, `scripts/`, `app/`, `reporting/`,
`.ci/`), so all three interfaces run in the container. Download the two data files as in Option A
first (into `./data`, which the container mounts), then:

```bash
docker compose build
docker compose run --rm datatool python scripts/load_raw.py
docker compose run --rm datatool dbt build --project-dir dbt_project --profiles-dir .ci
docker compose run --rm datatool python -m cli.main summary --date 2024-01-15 --top 5
```

Board pack — the container writes into `/app/data`, which `docker-compose.yml` mounts to `./data`
on the host, so the output file lands next to your other data files with no extra flags:

```bash
docker compose run --rm datatool \
    python -m cli.main report --month 2024-01 --output /app/data/board_pack.pptx --ai
# -> ./data/board_pack.pptx on the host
```

Dashboard — `docker-compose.yml` publishes `8501:8501`, but `docker compose run` only wires up a
service's ports when you pass `--service-ports`; Streamlit also needs to bind `0.0.0.0` instead of
its default `localhost` to be reachable from outside the container:

```bash
docker compose run --rm --service-ports datatool \
    streamlit run app/dashboard.py --server.address=0.0.0.0 --server.port=8501
# -> http://localhost:8501
```

Pass `-e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY` (or set it in a `.env` file next to
`docker-compose.yml`) to either command to enable the AI features.

Packing in Streamlit, Plotly, python-pptx, and Kaleido to support the dashboard and the report
command adds roughly 300MB to the image versus a CLI-only build — Kaleido alone bundles a ~220MB
headless renderer for exporting charts to PNG. That's the cost of one image serving all three
interfaces instead of a slimmer, CLI-only one.

**I could not build or run this image in this sandbox — Docker isn't installed here.** To verify
these changes yourself:

```bash
docker compose build
docker compose run --rm datatool python scripts/load_raw.py
docker compose run --rm datatool dbt build --project-dir dbt_project --profiles-dir .ci
docker compose run --rm datatool python -m cli.main report --month 2024-01 --output /app/data/board_pack.pptx
docker compose run --rm --service-ports datatool streamlit run app/dashboard.py --server.address=0.0.0.0 --server.port=8501
# then open http://localhost:8501 and confirm the dashboard loads
```

### The three interfaces

**CLI**

```bash
$ python -m cli.main summary --date 2024-01-15 --top 3
                         NYC Taxi Summary — 2024-01-15
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Zone               ┃ Borough   ┃ Trips ┃ Avg Fare ┃ Avg Mins ┃     Revenue ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ JFK Airport        │ Queens    │ 5,372 │   $64.29 │     37.7 │ $444,892.55 │
```

`python -m cli.main analyse --date 2024-01-15` sends the same data to Claude for a written summary
(requires `ANTHROPIC_API_KEY`).

**Dashboard**

```bash
streamlit run app/dashboard.py
```

Four tabs: Explorer (filter + ask Claude), Executive Overview (month KPIs, trend, top zones, board
pack download), Operational Insights (hourly heatmap, airport split, tip patterns), AI Analyst
(free-text Q&A). See `app/README.md` for details.

![Dashboard — Executive Overview](docs/dashboard-executive-overview.png)

**Board pack (PowerPoint)**

```bash
python -m cli.main report --month 2024-01 --output board_pack.pptx
python -m cli.main report --month 2024-01 --output board_pack.pptx --ai   # adds AI-written insights
```

Produces a 6-slide deck: title, executive summary (KPI tiles + optional AI insights), daily trend,
top zones by revenue, hourly demand heatmap, methodology.

Everything above works with no `ANTHROPIC_API_KEY` set except `analyse`, the dashboard's AI Analyst
tab and Analyse-with-AI button, and the `--ai` report flag — those fail gracefully with setup
guidance rather than erroring.

## Ingestion modes

`scripts/load_raw.py --source [local|ci|azure]` (default `local`) loads the raw parquet + zone CSV
into DuckDB's `nyc_tlc` schema. All three modes share the same `CREATE OR REPLACE TABLE` logic — only
where the bytes come from changes:

- **`local`** (default) — reads the two files from the local `data/` directory via `read_parquet` /
  `read_csv_auto`. What the Quickstart above uses.
- **`ci`** — reads the small fixture committed at `tests/fixtures/`, no real dataset or credentials
  needed. What CI uses (`load_raw.py --source ci`).
- **`azure`** — reads directly from a private Azure Blob container, no local download step. Installs
  DuckDB's `azure` extension, authenticates with `AZURE_STORAGE_CONNECTION_STRING`, and reads
  `azure://<container>/...` paths. Requires `AZURE_STORAGE_CONNECTION_STRING` and
  `CAPSTONE_AZURE_CONTAINER` — copy `.env.example` to `.env` and fill them in (or export them in your
  shell); the command exits with a clear error naming whichever is missing.

```bash
cp .env.example .env   # fill in AZURE_STORAGE_CONNECTION_STRING and CAPSTONE_AZURE_CONTAINER
python scripts/load_raw.py --source azure
```

Local and CI modes work with no Azure account or credentials at all — `azure` is an additional mode,
not a requirement.

### Provisioning the Azure container

These are the actual `az` CLI commands used to set up the private container this project reads
from — reproduce them under your own subscription (`az login` first), swapping in your own
resource group / storage account names and keeping the account key out of shell history:

```bash
az group create --name rg-capstone --location uksouth

# Storage account names are globally unique, lowercase alphanumeric, 3-24 chars.
az storage account create \
  --name <your-globally-unique-name> \
  --resource-group rg-capstone \
  --location uksouth \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

ACCOUNT_KEY=$(az storage account keys list \
  --account-name <your-globally-unique-name> \
  --resource-group rg-capstone \
  --query "[0].value" -o tsv)

az storage container create \
  --name raw \
  --account-name <your-globally-unique-name> \
  --account-key "$ACCOUNT_KEY" \
  --public-access off

az storage blob upload \
  --account-name <your-globally-unique-name> \
  --account-key "$ACCOUNT_KEY" \
  --container-name raw \
  --name yellow_tripdata_2024-01.parquet \
  --file data/yellow_tripdata_2024-01.parquet

az storage blob upload \
  --account-name <your-globally-unique-name> \
  --account-key "$ACCOUNT_KEY" \
  --container-name raw \
  --name taxi_zone_lookup.csv \
  --file data/taxi_zone_lookup.csv

# Prints the connection string for .env — pipe it straight into a secrets manager
# or your .env file rather than leaving it in scroll-back.
az storage account show-connection-string \
  --name <your-globally-unique-name> \
  --resource-group rg-capstone \
  --query connectionString -o tsv
```

If you're on a fresh Azure subscription, `az storage account create` may fail with
`SubscriptionNotFound` the first time — that means the `Microsoft.Storage` resource provider
isn't registered yet. Run `az provider register --namespace Microsoft.Storage` and retry once
`az provider show --namespace Microsoft.Storage --query registrationState` reports `Registered`.

On some Linux setups, DuckDB's `azure` extension fails to open blobs with a `Problem with the SSL
CA cert` error under its default HTTP transport — `load_raw.py` already works around this by
setting `azure_transport_option_type='curl'`, which uses the system's own TLS stack.

## Data quality & testing

Tests are layered by intent. Generic dbt tests (`not_null`, `accepted_values`, `relationships`)
guard every mart and staging column. Singular tests in `dbt_project/tests/` cover the things generic
tests can't express — for example:

- `assert_mart_trip_summary_revenue_reconciles.sql` — fails if `mart_trip_summary`'s total revenue
  drifts from `int_trips_enriched`'s by more than a cent per group.
- `assert_mart_trip_summary_unique_grain.sql` / `assert_mart_daily_kpis_unique_grain.sql` /
  `assert_mart_hourly_patterns_unique_grain.sql` — each mart's declared grain actually holds.
- `assert_int_trips_enriched_no_fanout.sql` — the zone joins in the intermediate layer don't
  inflate or drop rows.

71 dbt tests + 14 pytest tests run on every push (`dbt build`, then `pytest tests/`).

**The speed-units bug.** `avg_speed_mph` was originally computed as
`trip_distance / trip_duration_minutes` — miles per *minute*, not per hour, so every value read 60x
too low and a naive `< 100` plausibility bound let everything through unnoticed. Code review caught
the unit error. Fixing it (`× 60`) immediately pushed real bad-data rows — trips like 26 miles in 2
minutes — above a proper 80mph bound. A follow-up pass tightened the exemption for sub-2-minute
trips (duration truncates to whole minutes, which can inflate their computed speed) with an explicit
3-mile distance cap, since even 80mph sustained for 2 minutes only covers ~2.6 miles. Together these
filters exclude 375 physically-impossible rows out of ~2.96M in the raw January 2024 file. The
takeaway: a unit bug and a naive bound had been quietly hiding bad data, and only tightening the test
around the fix surfaced it.

Pytest (`tests/`) covers CLI behaviour (`test_cli.py`), deck generation (`test_deck_builder.py`),
and the LLM helper with the API mocked out (`test_llm.py`) — no application logic is left untested
by dbt's data checks.

CI (`.github/workflows/ci.yml`) needs no cloud credentials and no full dataset: it loads
`tests/fixtures/sample_trips.parquet` (a small committed fixture, via `load_raw.py --source ci`) into a
throwaway `data/ci_test.duckdb`, runs `dbt build --profiles-dir .ci` against it, then `pytest`. The
same fixture backs the CLI and deck-builder pytest suites, so CI never touches the real ~2.96M-row
dataset or an API key.

## Design decisions

**Why DuckDB, not a client-server database.** The workload is single-user OLAP over a few million
rows — DuckDB fits that exactly, ships as a single file with no server to run, and dbt-duckdb means
swapping the engine later (Postgres, Snowflake, MotherDuck) is a profile change, not a rewrite. The
trade-off: no concurrent writers, no row-level access control — fine for a portfolio project, not for
a shared production warehouse.

**Why the intermediate layer is ephemeral.** `int_trips_enriched` only exists to join zone lookups
onto the trip grain and compute a few derived columns before the marts aggregate it; it's never
queried on its own. `+materialized: ephemeral` inlines it as a CTE into each mart at compile time
instead of persisting a table nobody reads directly.

**Why marts are purpose-built per consumer**, not one wide table. `mart_trip_summary` is
trip_date × pickup_zone grain for the Explorer tab's drill-down; `mart_daily_kpis` is trip_date grain
for month-level trend lines; `mart_hourly_patterns` is day-of-week × hour grain for demand-pattern
analysis and doesn't carry a date at all. Each is sized and shaped for what queries it, rather than
forcing every consumer to re-aggregate a single fact table.

**The report-factory pattern.** `reporting/deck_builder.py` has no Streamlit import and takes a
plain `(db_path, month, ...)` signature, so it's callable from the CLI's `report` command, the
dashboard's download button, or (not yet built) a scheduled job — one deck-building codepath instead
of three. `reporting/figures.py` is factored out the same way so the dashboard's charts and the
deck's charts are pixel-consistent.

**Known limitations, stated plainly:**
- Only January 2024 is loaded — `stg_yellow_trips` hard-filters to that month by design, to keep the
  portfolio dataset small and predictable rather than because of a scaling limit.
- `mart_hourly_patterns` has no month grain — it aggregates the full dataset, so a board pack for any
  month currently shows the same demand heatmap. A month column would be a small, mechanical fix.
- The `azure` ingestion mode (see [Ingestion modes](#ingestion-modes)) reads a fixed pair of blob
  names from a single container — no manifest or multi-file glob yet, so a differently-organized
  container needs a small code change, not just new env vars.

## Project structure

```
cli/                  Click CLI (datatool entrypoint): summary, analyse, report commands
  main.py
  llm.py               Anthropic API wrapper, shared by the CLI, dashboard, and deck builder
dbt_project/
  models/
    staging/            1:1 cleaned views over the raw source tables
    intermediate/        ephemeral enrichment layer (zone joins, derived metrics)
    marts/               mart_trip_summary, mart_daily_kpis, mart_hourly_patterns
  tests/                singular (assert_*.sql) data tests
app/
  dashboard.py         4-tab Streamlit app
reporting/
  figures.py            shared plotly figure builders
  deck_builder.py       build_deck() — standalone PowerPoint generator
scripts/
  load_raw.py          loads parquet + zone CSV into DuckDB (--source local|ci|azure)
tests/                 pytest suite + CI fixtures
.github/workflows/     CI: lint, dbt build, pytest
.ci/profiles.yml       committed dbt profile (path from DBT_DB_PATH), used by CI and locally
```

## Development

```bash
uv sync --group dev
ruff check cli/ scripts/ reporting/
pytest tests/ -v --ignore=tests/fixtures
```

To run dbt without the API-key-free CI dataset, point `DBT_DB_PATH` at the real database and use the
same `.ci` profile (see Quickstart) — it's a generic DuckDB profile, not CI-specific despite the
directory name.

---

Built by [Qamar Raza](https://github.com/qraza) as a portfolio project. Data from
[NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
