# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FIU MSIS Projects repository — data engineering projects for the Master of Science in Information Systems program at Florida International University. The primary project is a YouTube Trending Data ETL pipeline built on a modern data stack: **Prefect** for orchestration, **dbt** for transformation, **Snowflake** as the data warehouse, and **Azure Static Web Apps** for hosting dbt documentation.

## Repository Structure

```
fiumsis/
├── .github/
│   └── workflows/
│       └── azure-static-web-apps-zealous-sea-0b839900f.yml  # CI/CD: dbt docs → Azure
├── fiu_dbt/                        # dbt project
│   ├── models/
│   │   ├── overview.md             # dbt docs homepage
│   │   └── yt_trending_data/       # YouTube trending data model group
│   │       ├── _yt_trending_data__models.yml  # Schema, tests, descriptions
│   │       ├── dim_category.sql
│   │       ├── dim_channel.sql
│   │       ├── dim_video.sql
│   │       └── fact_yt_trending.sql
│   ├── analyses/, macros/, seeds/, snapshots/, tests/  # empty, reserved
│   └── dbt_project.yml
├── projects/
│   └── YouTube/
│       ├── yt_trending_data.py     # Prefect ETL flow (main entrypoint)
│       └── pbi_dashboard.zip       # Power BI dashboard (Git LFS)
├── profiles.yml                    # dbt Snowflake connection (at repo root)
├── prefect.yaml                    # Prefect deployment config
├── .gitattributes                  # *.pbix → Git LFS
└── CLAUDE.md                       # This file
```

## Architecture

A three-layer pipeline:

```
Kaggle API
    ↓ yt_trending_data_pull()
Snowflake Staging Tables
    ├── STG_US_YT_TRENDING  (CSV data)
    └── STG_US_YT_CATEGORY  (JSON category data)
    ↓ yt_dbt_model() → dbt build
Snowflake Star Schema (CLASS_PROJECT.YT_TRENDING_DATA)
    ├── dim_video
    ├── dim_channel
    ├── dim_category
    └── fact_yt_trending
    ↓ GitHub Actions (push to main)
Azure Static Web Apps
    └── dbt documentation site
```

### Layer 1 — Prefect (`projects/YouTube/yt_trending_data.py`)

Orchestrates the ETL flow with three tasks and one flow:

| Name | Type | Purpose |
|------|------|---------|
| `yt_trending_data_pull` | `@task` | Downloads US YouTube trending CSV + US_category_id.json from Kaggle; normalizes JSON (strips `snippet.` prefixes); returns two DataFrames |
| `yt_trending_data_load` | `@task` | Bulk-loads DataFrames into Snowflake staging tables using `overwrite=True` (full refresh each run) |
| `yt_dbt_model` | `@task` | Runs `dbt build --select yt_trending_data` via `PrefectDbtRunner` |
| `yt_trending_data` | `@flow(retries=1)` | Main flow: loads Snowflake credentials from Prefect Blocks, sets env vars for dbt, chains the three tasks |

**Prefect Blocks required at runtime:**
- `snowflake-credentials` — Snowflake connection block
- `kaggle-username` — Kaggle API username (Secret block)
- `kaggle-key` — Kaggle API key (Secret block)

**Snowflake targets:**
- Database: `CLASS_PROJECT`
- Schema: `YT_TRENDING_DATA`
- Staging tables: `STG_US_YT_TRENDING`, `STG_US_YT_CATEGORY`

### Layer 2 — dbt (`fiu_dbt/`)

Transforms staging data into a star schema. All models use `incremental` materialization with `merge` strategy.

**Dimension tables** (surrogate keys via Snowflake sequences):

| Model | Natural Key | Sequence | Deduplication Logic |
|-------|-------------|----------|---------------------|
| `dim_video` | `VIDEO_ID` | `DIM_VIDEO_SEQ.NEXTVAL` | `ROW_NUMBER() PARTITION BY VIDEO_ID ORDER BY VIEW_COUNT DESC` |
| `dim_channel` | `CHANNELID` | `DIM_CHANNEL_SEQ.NEXTVAL` | `ROW_NUMBER() PARTITION BY CHANNELID ORDER BY VIEW_COUNT DESC` |
| `dim_category` | `CATEGORYID` | `DIM_CATEGORY_SEQ.NEXTVAL` | No deduplication needed |

**Fact table:**

| Model | Unique Key | Source |
|-------|------------|--------|
| `fact_yt_trending` | `[VIDEO_KEY, CHANNEL_KEY, CATEGORY_KEY]` | `STG_US_YT_TRENDING` joined to all three dims via `ref()` |

All models include `DW_CREATE_TS` and `DW_UPDATE_TS` audit timestamps. The `merge_exclude_columns` config prevents overwriting surrogate keys and create timestamps on merge.

**dbt tests** (defined in `_yt_trending_data__models.yml`):
- `unique` and `not_null` on all surrogate keys and natural keys
- `relationships` tests on fact table foreign keys pointing to dimension tables

### Layer 3 — Azure Static Web Apps (CI/CD)

GitHub Actions workflow (`.github/workflows/azure-static-web-apps-zealous-sea-0b839900f.yml`):
1. Triggered on push/PR to `main`
2. Sets up Python 3.11
3. Installs `dbt-core` + `dbt-snowflake`
4. Runs `dbt docs generate` (using Snowflake secrets from GitHub Actions secrets)
5. Deploys `fiu_dbt/target/` to Azure Static Web Apps

## Snowflake Connection

`profiles.yml` is at the **repo root** (not inside `fiu_dbt/`). This means all dbt commands must include `--profiles-dir .` when run from the repo root.

Environment variables read by `profiles.yml`:
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_PASSWORD`
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_SCHEMA`

For local runs, set these in your shell or a `.env` file (`.env` is gitignored). For Prefect-managed runs, the flow loads them from the `snowflake-credentials` Prefect Block.

## Key Commands

**Run the full ETL flow locally:**
```bash
python projects/YouTube/yt_trending_data.py
```

**dbt commands (always run from repo root):**
```bash
# Build all yt_trending_data models (run + test)
dbt build --select yt_trending_data --profiles-dir . --project-dir fiu_dbt

# Run only (skip tests)
dbt run --select yt_trending_data --profiles-dir . --project-dir fiu_dbt

# Test only
dbt test --select yt_trending_data --profiles-dir . --project-dir fiu_dbt

# Generate and serve documentation
dbt docs generate --profiles-dir . --project-dir fiu_dbt
dbt docs serve --project-dir fiu_dbt
```

**Deploy Prefect flow to work pool:**
```bash
prefect deploy --name YouTube-Trending-ETL
```

**Prefect deployment config** (`prefect.yaml`):
- Work pool: `fiu-msis-workpool`
- Project: `ism6316-project`
- Entrypoint: `projects/YouTube/yt_trending_data.py:yt_trending_data`
- Pull step: git clone from `https://github.com/c85/fiumsis` (main branch)

## Package Versions

Pinned in `prefect.yaml` pip install step:

| Package | Version |
|---------|---------|
| dbt-core | 1.11.3 |
| dbt-snowflake | 1.11.1 |
| prefect-snowflake | 0.28.0 |
| prefect-dbt | 0.7.16 |
| kaggle | 1.5.16 |
| snowflake-connector-python | 4.2.0 |
| pandas | (latest) |

## Conventions and Patterns

### dbt Conventions
- All SQL uses **uppercase** identifiers (Snowflake convention)
- Surrogate keys follow the pattern `<DIM_NAME>_KEY` (e.g., `VIDEO_KEY`, `CHANNEL_KEY`)
- Sequences are pre-created in Snowflake: `DIM_VIDEO_SEQ`, `DIM_CHANNEL_SEQ`, `DIM_CATEGORY_SEQ`
- Every model gets `DW_CREATE_TS` (CURRENT_TIMESTAMP() on first insert) and `DW_UPDATE_TS` (CURRENT_TIMESTAMP() on every merge)
- Deduplication uses `QUALIFY ROW_NUMBER() OVER (...)` inline — no CTEs for dedup
- `merge_exclude_columns` must list surrogate key column + `DW_CREATE_TS` to protect them from being overwritten

### Python Conventions
- Prefect tasks are decorated with `@task`, flows with `@flow`
- Logger obtained via `get_run_logger()` inside tasks/flows
- Credentials never hardcoded — always from Prefect Blocks or environment variables
- Kaggle downloads go to the current working directory then get cleaned up

### Git Conventions
- Binary files (`.pbix`) use Git LFS (configured in `.gitattributes`)
- `fiu_dbt/target/`, `fiu_dbt/dbt_packages/`, `fiu_dbt/logs/` are gitignored
- Branch `main` triggers CI/CD deployment to Azure

## Adding New Projects

1. Create `projects/<ProjectName>/` with a Prefect flow script
2. Add dbt models under `fiu_dbt/models/<model_group>/` if transformation is needed
3. Define model schema, tests, and descriptions in `_<model_group>__models.yml`
4. Add a deployment entry to `prefect.yaml` if scheduling is required
5. GitHub Actions will automatically include the new dbt models in docs generation on push to `main`
