# orchestrator/assets/workforce_preparation.py
from dagster import asset, AssetExecutionContext, multi_asset, AssetOut, AssetIn
from orchestrator.resources import DuckDBResource, DbtResource
from orchestrator.utils.cold_start_validation import (
    validate_workforce_initialization,
    check_schema_compatibility
)
from typing import Dict, Any
import pandas as pd

@asset(
    deps=["stg_census_data"],
    description="Run dbt models for workforce baseline preparation"
)
def workforce_baseline_models(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    dbt: DbtResource
) -> None:
    """Run all workforce baseline preparation models"""

    # First check schema compatibility
    if not check_schema_compatibility(context, duckdb):
        raise Exception("Schema compatibility check failed between census and workforce tables")

    # Run dbt models in correct order
    dbt_models = [
        "int_cold_start_detection",
        "int_baseline_workforce",
        "int_workforce_previous_year",
        "int_year_snapshot_preparation"
    ]

    context.log.info(f"Running workforce baseline models: {', '.join(dbt_models)}")
    dbt_results = dbt.run(dbt_models)

    if not dbt_results.success:
        raise Exception(f"dbt model execution failed: {dbt_results.results}")

@asset(
    deps=["workforce_baseline_models"],
    description="Validate workforce initialization after all models complete"
)
def workforce_initialization_validation(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> Dict[str, Any]:
    """Validate workforce initialization after all models have run"""

    simulation_year = context.run.run_config.get("simulation_year", 1)

    # Perform comprehensive validation
    validation_result = validate_workforce_initialization(context, duckdb, simulation_year)

    # Log validation results
    context.log.info(f"Workforce initialization validation: {validation_result['validation_status']}")
    for check in validation_result["checks"]:
        log_method = context.log.info if check["passed"] else context.log.warning
        log_method(f"  - {check['check_name']}: {check['message']}")

    if validation_result["validation_status"] == "FAILED":
        raise Exception(
            f"Workforce initialization validation failed for year {simulation_year}. "
            f"Failed checks: {[c['check_name'] for c in validation_result['checks'] if not c['passed']]}"
        )

    return validation_result

@asset(
    ins={"validation": AssetIn("workforce_initialization_validation")},
    description="Return validated workforce data for downstream processing"
)
def validated_workforce_baseline(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    validation: Dict[str, Any]
) -> pd.DataFrame:
    """Return validated workforce baseline data"""

    simulation_year = context.run.run_config.get("simulation_year", 1)

    with duckdb.get_connection() as conn:
        workforce_df = conn.execute("""
            SELECT
                employee_id,
                employee_ssn,
                employee_birth_date,
                employee_hire_date,
                employee_gross_compensation,
                current_age,
                current_tenure,
                level_id,
                age_band,
                tenure_band,
                employment_status,
                termination_date,
                termination_reason,
                simulation_year,
                effective_date,
                is_from_census,
                is_cold_start,
                last_completed_year
            FROM int_year_snapshot_preparation
            WHERE employment_status = 'active'
        """).df()

    context.log.info(
        f"Returning validated workforce baseline with {len(workforce_df)} active employees"
    )

    return workforce_df
