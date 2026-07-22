# CLAUDE.md

Guidance for Claude Code when working in this repo. See `README.md` for the full project
description, architecture, and quickstart — this file is process notes, not a duplicate of it.

## Conventions

- dbt SQL: CTE-per-source, `round(..., n)` on aggregates, singular tests named
  `assert_<model>_<check>.sql` in `dbt_project/tests/`, generic `not_null` / `accepted_values` /
  `relationships` tests declared in each layer's `schema.yml`.
- `reporting/` has no Streamlit imports — it's called by both `cli/main.py` and `app/dashboard.py`,
  keep it that way.
- Local dbt runs can use the committed `.ci/profiles.yml` (reads `DBT_DB_PATH` from the
  environment) instead of a personal `~/.dbt/profiles.yml` — see README Quickstart.
- Don't push to origin unless explicitly asked, even after commits are made and verified — work is
  reviewed locally first.
- `scripts/jira_client.py` is workflow-only (ADF flatten/build helpers, `get_issue`,
  `post_comment`, `find_request_to_implement`, `build_prompt`) — no CLI/dashboard/reporting code
  imports it.

## Jira-triggered agent (`.github/workflows/jira-agent.yml`)

- Triggers: `repository_dispatch` (type `jira-approved`, issue key at
  `client_payload.issue_key`) and `workflow_dispatch` (manual `issue_key` input, for testing
  before the live webhook is wired up — see README).
- Required repo secrets: `CLAUDE_CODE_OAUTH_TOKEN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
  `JIRA_BASE_URL`.
- The Jira Automation rule that posts the `jira-approved` webhook on an "Approved" comment is
  configured manually in the Jira UI, not in this repo — there's nothing here to keep in sync
  with it beyond the `client_payload.issue_key` shape the workflow expects.
- The agent works on a `jira/<ISSUE-KEY>` branch and is blocked (via `claude_args`
  `--disallowedTools`) from editing `.github/workflows/**`, `.env*`, or `.ci/**`; it only opens a
  PR if ruff, pytest, and `dbt build --profiles-dir .ci` all pass.

## Roadmap

- [x] Root `README.md`
- [x] MIT `LICENSE`
- [x] Dockerfile/docker-compose cover the full project (dashboard + report command, not just the CLI)
- [ ] MotherDuck (or other hosted DuckDB) deployment for the dashboard, so it's not local-only
- [ ] Give `mart_hourly_patterns` a month grain (currently aggregates the full dataset regardless
      of the month a board pack is generated for)
- [x] Cloud ingestion layer — `scripts/load_raw.py --source azure` reads the raw parquet + zone CSV
      directly from a private Azure Blob container via DuckDB's `azure` extension, no local
      download step
- [ ] Refactor hardcoded `~/development/capstone-data-tool` absolute paths (`cli/main.py`,
      `app/dashboard.py`, `scripts/load_raw.py`, dbt profile) to derive from the project root —
      improves portability for anyone cloning to a different location, and unblocks renaming the
      local folder
