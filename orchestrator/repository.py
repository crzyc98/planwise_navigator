"""Dagster repository for PlanWise Navigator simulation pipeline.

This module defines the complete orchestration workflow using Dagster, integrating
the dbt models as assets and providing a scheduled job for regular execution.

The pipeline workflow:
1. Ingest raw census data into DuckDB
2. Execute dbt models to transform and process the data
3. All steps are orchestrated as a single job with proper dependencies
"""
from pathlib import Path
from typing import Any

from dagster import (
    AssetSelection,
    Definitions,
    asset,
    define_asset_job,
    schedule,
    Config,
)
from dagster_dbt import DbtCliResource, dbt_assets
from orchestrator.simulator_pipeline import execute_dbt_command_streaming

# Local imports
from .connect_db import get_connection
from .ingest_data import ingest, describe_table, validate_row_counts, summary_stats

# Project paths
DBT_PROJECT_DIR = Path(__file__).resolve().parent.parent / "dbt"
DBT_PROFILES_DIR = DBT_PROJECT_DIR
DATA_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "census_preprocessed.parquet"
)


class IngestionConfig(Config):
    """Configuration for the ingestion operation."""

    data_file_path: str = str(DATA_FILE)


# Configure dbt CLI resource
dbt_resource = DbtCliResource(
    project_dir=str(DBT_PROJECT_DIR),
    profiles_dir=str(DBT_PROFILES_DIR),
    dbt_executable=str(Path(__file__).parent.parent / "venv" / "bin" / "dbt"),
)


@dbt_assets(manifest=DBT_PROJECT_DIR / "target" / "manifest.json")
def planwise_dbt_assets(context, dbt: DbtCliResource):
    """Collection of dbt assets representing the transformation pipeline.

    This uses the @dbt_assets factory to automatically parse the dbt manifest
    and create Dagster assets for all dbt models, with proper dependencies.
    """
    yield from execute_dbt_command_streaming(
        context,
        ["build"],
        {},
        False,
        "full dbt build pipeline"
    )


@asset(description="Ingest census data from Parquet file into DuckDB census_raw table")
def ingest_census_data(context) -> str:
    """Ingest census data into DuckDB and perform validation.

    This operation:
    1. Connects to the DuckDB database
    2. Creates or replaces the census_raw table from Parquet data
    3. Validates the ingestion with row counts and schema inspection
    4. Computes summary statistics on numeric columns

    Returns:
        str: Status message indicating successful ingestion
    """
    context.log.info(f"Starting census data ingestion from {DATA_FILE}")

    # Get database connection
    con = get_connection()

    try:
        # Perform ingestion
        ingest(con)
        context.log.info("✅ Census data ingested successfully")

        # Validate and describe the data
        schema_rows = describe_table(con)
        validate_row_counts(con)
        summary_stats(con, schema_rows)

        # Get final row count for logging
        row_count = con.execute("SELECT COUNT(*) FROM census_raw").fetchone()[0]
        context.log.info(f"Final census_raw table contains {row_count} rows")

        return f"Successfully ingested {row_count} rows into census_raw table"

    except Exception as e:
        context.log.error(f"Failed to ingest census data: {str(e)}")
        raise
    finally:
        con.close()


@asset(
    description="Validation check that census_raw table exists and has data",
    deps=[ingest_census_data],
)
def census_data_validation(context) -> dict[str, Any]:
    """Validate that the census_raw table exists and contains expected data.

    Returns:
        dict: Validation results including row count and basic statistics
    """
    con = get_connection()

    try:
        # Check table exists and get basic info
        row_count = con.execute("SELECT COUNT(*) FROM census_raw").fetchone()[0]

        # Get column count
        columns = con.execute("DESCRIBE census_raw").fetchall()
        column_count = len(columns)

        validation_results = {
            "table_exists": True,
            "row_count": row_count,
            "column_count": column_count,
            "columns": [col[0] for col in columns],
        }

        context.log.info(
            f"Census data validation passed: {row_count} rows, {column_count} columns"
        )
        return validation_results

    except Exception as e:
        context.log.error(f"Census data validation failed: {str(e)}")
        raise
    finally:
        con.close()


# Define the main simulation job
simulation_job = define_asset_job(
    name="simulation_job",
    description="Complete workforce simulation pipeline from ingestion to final models",
    selection=AssetSelection.all(),
    tags={"pipeline": "workforce_simulation"},
)


@schedule(
    job=simulation_job,
    cron_schedule="0 2 * * *",  # Daily at 2 AM
    tags={"schedule": "daily"},
)
def daily_simulation_schedule(context):
    """Schedule the simulation job to run daily at 2 AM.

    This schedule ensures the workforce simulation pipeline runs automatically
    on a regular basis, providing fresh results for analysis.
    """
    return {}


@schedule(
    job=simulation_job,
    cron_schedule="0 2 * * 0",  # Weekly on Sunday at 2 AM
    tags={"schedule": "weekly"},
)
def weekly_simulation_schedule(context):
    """Schedule the simulation job to run weekly on Sunday at 2 AM.

    Alternative schedule for less frequent pipeline execution.
    """
    return {}


# Define all Dagster definitions for this repository
defs = Definitions(
    assets=[
        ingest_census_data,
        planwise_dbt_assets,
        census_data_validation,
    ],
    jobs=[simulation_job],
    schedules=[
        daily_simulation_schedule,
        weekly_simulation_schedule,
    ],
    resources={
        "dbt": dbt_resource,
    },
)
