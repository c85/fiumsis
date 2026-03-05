# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FIU MSIS Projects repository — data engineering projects for the Master of Science in Information Systems program at Florida International University. The primary project is a YouTube Trending Data ETL pipeline.

## Architecture

This is a data pipeline stack with three layers:

1. **Prefect** (`projects/YouTube/yt_trending_data.py`) — orchestrates the ETL flow:
   - `yt_trending_data_pull`: downloads US YouTube trending CSV and category JSON from Kaggle
   - `yt_trending_data_load`: bulk-loads staging tables in Snowflake (`STG_US_YT_TRENDING`, `STG_US_YT_CATEGORY`)
   - `yt_dbt_model`: triggers dbt build for the `yt_trending_data` model group

2. **dbt** (`fiu_dbt/`) — transforms staging data into a star schema in Snowflake (`CLASS_PROJECT.YT_TRENDING_DATA`):
   - `dim_video`, `dim_channel`, `dim_category` — incremental dimension tables using Snowflake sequences for surrogate keys
   - `fact_yt_trending` — fact table joining the three dims; uses `qualify row_number()` to deduplicate

3. **Azure Static Web Apps** (CI/CD via `.github/workflows/`) — deploys dbt docs (`fiu_dbt/target/`) to Azure on push to `main`

## Snowflake Connection

dbt connects via environment variables. The `profiles.yml` at repo root (not inside `fiu_dbt/`) reads:
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`

When running locally, set these vars or use `.env`. Prefect stores credentials in Prefect Blocks (`snowflake-credentials`, `kaggle-username`, `kaggle-key`).

## Key Commands

**Run the full ETL flow locally:**
```bash
python projects/YouTube/yt_trending_data.py
```

**dbt commands (run from repo root, profiles.yml is at root):**
```bash
# Build all yt_trending_data models
dbt build --select yt_trending_data --profiles-dir . --project-dir fiu_dbt

# Run only (no tests)
dbt run --select yt_trending_data --profiles-dir . --project-dir fiu_dbt

# Generate and serve docs
dbt docs generate --profiles-dir . --project-dir fiu_dbt
dbt docs serve --project-dir fiu_dbt
```

**Deploy Prefect flow:**
```bash
prefect deploy --name YouTube-Trending-ETL
```

## Package Versions (from prefect.yaml)

- `dbt-core==1.11.3`, `dbt-snowflake==1.11.1`
- `prefect-snowflake==0.28.0`, `prefect-dbt==0.7.16`
- `kaggle==1.5.16`, `snowflake-connector-python==4.2.0`

## New Projects

Add new projects under `projects/<ProjectName>/`. Each project should have its own Prefect flow and, if needed, dbt models under `fiu_dbt/models/<model_group>/`.
