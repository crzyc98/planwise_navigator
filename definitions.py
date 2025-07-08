"""PlanWise Navigator Dagster definitions."""

from dagster import Definitions
from dagster_dbt import DbtCliResource

from orchestrator.assets import (
    planwise_dbt_assets,
    simulation_config,
    census_data_validation,
    run_single_year_simulation,
    workforce_analytics,
    simulation_report_data,
    # S047 Optimization Engine assets
    advanced_optimization_engine,
    optimization_sensitivity_analysis,
    optimization_evidence_report,
)
from orchestrator.resources.duckdb_resource import DuckDBResource
from pathlib import Path

# Import jobs from simulator_pipeline and repository
from orchestrator.simulator_pipeline import (
    single_year_simulation,  # This is a job
    multi_year_simulation,  # This is a job
)
from orchestrator.repository import simulation_job  # This is a job


# Define paths
PROJECT_ROOT = Path(__file__).parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"
DBT_PROFILES_DIR = DBT_PROJECT_DIR

defs = Definitions(
    assets=[
        planwise_dbt_assets,
        simulation_config,
        census_data_validation,
        # Note: run_single_year_simulation is a multi_asset, not a job,
        # so it remains in the 'assets' list.
        run_single_year_simulation,
        workforce_analytics,
        simulation_report_data,
        # S047 Optimization Engine assets
        advanced_optimization_engine,
        optimization_sensitivity_analysis,
        optimization_evidence_report,
    ],
    # ADD THE JOBS HERE
    jobs=[
        single_year_simulation,
        multi_year_simulation,
        simulation_job,
    ],
    resources={
        "dbt": DbtCliResource(
            project_dir=str(DBT_PROJECT_DIR),
            profiles_dir=str(DBT_PROFILES_DIR),
            dbt_executable=str(PROJECT_ROOT / "venv" / "bin" / "dbt"),
        ),
        "duckdb_resource": DuckDBResource(
            database_path=str(PROJECT_ROOT / "simulation.duckdb"),
            read_only=False,
        ),
    },
)
