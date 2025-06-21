# filename: orchestrator/assets.py
"""PlanWise Navigator Dagster asset definitions."""

from dagster import (
    asset, 
    AssetExecutionContext, 
    AssetIn, 
    multi_asset,
    AssetOut,
    Output
)
from dagster_dbt import DbtCliResource, dbt_assets
import pandas as pd
from typing import Dict, Any, List
from pathlib import Path

from ..resources.duckdb_resource import DuckDBResource
from ..config.schema import SimulationConfig

# dbt asset integration
DBT_PROJECT_DIR = Path(__file__).parent.parent / "dbt"
DBT_PROFILES_DIR = DBT_PROJECT_DIR

@dbt_assets(
    manifest=DBT_PROJECT_DIR / "target" / "manifest.json",
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROFILES_DIR,
)
def planwise_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Execute dbt models for PlanWise Navigator."""
    yield from dbt.cli(["build"], context=context).stream()

@asset
def simulation_config(context: AssetExecutionContext) -> Dict[str, Any]:
    """Load and validate simulation configuration."""
    # TODO: Load from YAML file path configured in run config
    config = SimulationConfig(
        start_year=2025,
        end_year=2029,
        target_growth_rate=0.03,
        total_termination_rate=0.12,
        new_hire_termination_rate=0.25,
        random_seed=42
    )
    
    context.log.info(f"Loaded config for years {config.start_year}-{config.end_year}")
    return config.dict()

@asset(deps=[simulation_config])
def census_data_validation(
    context: AssetExecutionContext, 
    duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Validate census data quality before simulation."""
    with duckdb_resource.get_connection() as conn:
        # Check for required tables
        validation_results = {}
        
        # Row count check
        row_count = conn.execute(
            "SELECT COUNT(*) FROM stg_census_data"
        ).fetchone()[0]
        validation_results["row_count"] = row_count
        
        # Null checks
        null_counts = conn.execute("""
            SELECT 
                SUM(CASE WHEN employee_id IS NULL THEN 1 ELSE 0 END) as null_ids,
                SUM(CASE WHEN level_id IS NULL THEN 1 ELSE 0 END) as null_levels
            FROM stg_census_data
        """).fetchone()
        
        validation_results["null_employee_ids"] = null_counts[0]
        validation_results["null_level_ids"] = null_counts[1]
        
        # Level distribution
        level_dist = conn.execute("""
            SELECT level_id, COUNT(*) as count
            FROM stg_census_data
            GROUP BY level_id
            ORDER BY level_id
        """).df()
        
        validation_results["level_distribution"] = level_dist.to_dict('records')
        
        context.log.info(f"Validated {row_count} employee records")
        return validation_results

@multi_asset(
    ins={
        "simulation_config": AssetIn(),
        "planwise_dbt_assets": AssetIn()
    },
    outs={
        "single_year_simulation": AssetOut(),
        "simulation_year_state": AssetOut()
    }
)
def run_single_year_simulation(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    simulation_config: Dict[str, Any]
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute single year of workforce simulation."""
    year = simulation_config["start_year"]  # TODO: Support multi-year
    
    with duckdb_resource.get_connection() as conn:
        # Set simulation parameters
        conn.execute(f"SET VARIABLE simulation_year = {year}")
        conn.execute(f"SET VARIABLE random_seed = {simulation_config['random_seed']}")
        
        # Run simulation by triggering dbt models
        # (Already executed via dbt asset dependency)
        
        # Fetch results
        workforce_df = conn.execute(f"""
            SELECT * FROM fct_workforce_snapshot
            WHERE simulation_year = {year}
        """).df()
        
        events_df = conn.execute(f"""
            SELECT event_type, COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = {year}
            GROUP BY event_type
        """).df()
        
        # Calculate state metrics
        state = {
            "year": year,
            "total_headcount": len(workforce_df),
            "events_summary": events_df.to_dict('records'),
            "avg_compensation": workforce_df["current_compensation"].mean()
        }
        
        context.log.info(f"Completed year {year}: {state['total_headcount']} employees")
        
    yield Output(workforce_df, output_name="single_year_simulation")
    yield Output(state, output_name="simulation_year_state")

@asset
def workforce_analytics(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    single_year_simulation: pd.DataFrame
) -> pd.DataFrame:
    """Generate analytical summaries from simulation results."""
    # Group by level
    level_summary = single_year_simulation.groupby('level_id').agg({
        'employee_id': 'count',
        'current_compensation': ['mean', 'median', 'std'],
        'current_age': 'mean',
        'current_tenure': 'mean'
    }).round(2)
    
    level_summary.columns = ['_'.join(col).strip() for col in level_summary.columns]
    level_summary = level_summary.reset_index()
    
    context.log.info(f"Generated analytics for {len(level_summary)} levels")
    return level_summary

@asset
def simulation_report_data(
    context: AssetExecutionContext,
    simulation_year_state: Dict[str, Any],
    workforce_analytics: pd.DataFrame
) -> Dict[str, Any]:
    """Prepare data for reporting dashboard."""
    report_data = {
        "simulation_state": simulation_year_state,
        "level_analytics": workforce_analytics.to_dict('records'),
        "generated_at": pd.Timestamp.now().isoformat()
    }
    
    context.log.info("Prepared simulation report data")
    return report_data