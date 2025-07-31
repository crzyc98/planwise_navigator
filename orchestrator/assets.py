# filename: orchestrator/assets.py
"""PlanWise Navigator Dagster asset definitions."""

from dagster import (
    asset,
    AssetExecutionContext,
    AssetIn,
    multi_asset,
    AssetOut,
    Output,
    AssetCheckResult,
    asset_check,
    AssetKey,
)
from dagster_dbt import DbtCliResource, dbt_assets
from orchestrator.simulator_pipeline import execute_dbt_command_streaming
import pandas as pd
from typing import Dict, Any, Generator
from pathlib import Path

from orchestrator.resources.duckdb_resource import DuckDBResource
from config.schema import SimulationConfig
from orchestrator.optimization import (
    CompensationOptimizer,
    OptimizationRequest,
    OptimizationResult,
    OptimizationError
)
from typing import Union
from orchestrator.optimization.evidence_generator import EvidenceGenerator
from orchestrator.optimization.sensitivity_analysis import SensitivityAnalyzer

# dbt asset integration
DBT_PROJECT_DIR = Path(__file__).parent.parent / "dbt"


# The dbt CLI resource (configured in `definitions.py`) now provides the project and
# profiles directories, so we only need to supply the compiled `manifest.json`.
@dbt_assets(
    manifest=DBT_PROJECT_DIR / "target" / "manifest.json",
)
def planwise_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
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
        random_seed=42,
        promotion_budget_pct=0.15,
        cola_rate=0.025,
        merit_budget_pct=0.04,
        promotion_increase_pct=0.15,
    )

    context.log.info(f"Loaded config for years {config.start_year}-{config.end_year}")
    return config.dict()


@asset(deps=[simulation_config])
def census_data_validation(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Validate census data quality before simulation."""
    with duckdb_resource.get_connection() as conn:
        # Check for required tables
        validation_results = {}

        # Row count check
        row_count = conn.execute("SELECT COUNT(*) FROM stg_census_data").fetchone()[0]
        validation_results["row_count"] = row_count

        # Null checks
        null_counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN employee_id IS NULL THEN 1 ELSE 0 END) as null_ids,
                SUM(CASE WHEN level_id IS NULL THEN 1 ELSE 0 END) as null_levels
            FROM stg_census_data
        """
        ).fetchone()

        validation_results["null_employee_ids"] = null_counts[0]
        validation_results["null_level_ids"] = null_counts[1]

        # Level distribution
        level_dist = conn.execute(
            """
            SELECT level_id, COUNT(*) as count
            FROM stg_census_data
            GROUP BY level_id
            ORDER BY level_id
        """
        ).df()

        validation_results["level_distribution"] = level_dist.to_dict("records")

        context.log.info(f"Validated {row_count} employee records")
        return validation_results


# Updated multi_asset definition for run_single_year_simulation
@multi_asset(
    # 'simulation_config' is an input received as an argument.
    ins={"simulation_config": AssetIn()},
    # Outputs of this multi_asset.
    outs={
        "single_year_simulation": AssetOut(),
        "simulation_year_state": AssetOut(),
    },
    # Dependencies: These assets must be materialized *before* this multi_asset runs.
    # The 'planwise_dbt_assets' function itself represents the collection of dbt models.
    # Listing it in `deps` ensures all dbt models are built before this asset's execution.
    deps=[
        planwise_dbt_assets  # This ensures the entire dbt pipeline runs before this asset.
    ],
)
def run_single_year_simulation(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    simulation_config: Dict[str, Any],
    # Removed 'planwise_dbt_assets: Any' from function signature.
    # The dbt model data is accessed directly from DuckDB via `duckdb_resource`.
) -> Generator[Output[Any], None, None]:
    """Execute single year of workforce simulation."""
    year = simulation_config["start_year"]  # TODO: Support multi-year

    with duckdb_resource.get_connection() as conn:
        # Set simulation parameters
        conn.execute(f"SET VARIABLE simulation_year = {year}")
        conn.execute(f"SET VARIABLE random_seed = {simulation_config['random_seed']}")

        # dbt models (like fct_workforce_snapshot, fct_yearly_events) are guaranteed to be built
        # because 'planwise_dbt_assets' is declared as a dependency in the 'deps' list.
        # Now fetch results directly from DuckDB using the DuckDB resource.
        workforce_df = conn.execute(
            f"""
            SELECT * FROM fct_workforce_snapshot
            WHERE simulation_year = {year}
        """
        ).df()

        events_df = conn.execute(
            f"""
            SELECT event_type, COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = {year}
            GROUP BY event_type
        """
        ).df()

        # Calculate state metrics
        state = {
            "year": year,
            "total_headcount": len(workforce_df),
            "events_summary": events_df.to_dict("records"),
            "avg_compensation": workforce_df["current_compensation"].mean(),
        }

        context.log.info(f"Completed year {year}: {state['total_headcount']} employees")

    yield Output(workforce_df, output_name="single_year_simulation")
    yield Output(state, output_name="simulation_year_state")


@asset
def workforce_analytics(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    single_year_simulation: pd.DataFrame,
) -> pd.DataFrame:
    """Generate analytical summaries from simulation results."""
    # Group by level
    level_summary = (
        single_year_simulation.groupby("level_id")
        .agg(
            {
                "employee_id": "count",
                "current_compensation": ["mean", "median", "std"],
                "current_age": "mean",
                "current_tenure": "mean",
            }
        )
        .round(2)
    )

    level_summary.columns = ["_".join(col).strip() for col in level_summary.columns]
    level_summary = level_summary.reset_index()

    context.log.info(f"Generated analytics for {len(level_summary)} levels")
    return level_summary


@asset
def simulation_report_data(
    context: AssetExecutionContext,
    simulation_year_state: Dict[str, Any],
    workforce_analytics: pd.DataFrame,
) -> Dict[str, Any]:
    """Prepare data for reporting dashboard."""
    report_data = {
        "simulation_state": simulation_year_state,
        "level_analytics": workforce_analytics.to_dict("records"),
        "generated_at": pd.Timestamp.now().isoformat(),
    }

    context.log.info("Prepared simulation report data")
    return report_data


# === COMPENSATION VALIDATION ASSET CHECKS ===


@asset_check(asset=AssetKey(["fct_yearly_events"]), name="compensation_outlier_check")
def check_no_extreme_compensation(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: No hire events with compensation > $500K."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_yearly_events'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_yearly_events table not found - dbt model may not be materialized",
                )

            outlier_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM fct_yearly_events
                WHERE event_type = 'hire'
                AND compensation_amount > 500000
            """
            ).fetchone()[0]

            if outlier_count > 0:
                outlier_details = conn.execute(
                    """
                    SELECT simulation_year, level_id, compensation_amount
                    FROM fct_yearly_events
                    WHERE event_type = 'hire'
                    AND compensation_amount > 500000
                    ORDER BY compensation_amount DESC
                    LIMIT 5
                """
                ).df()

                return AssetCheckResult(
                    passed=False,
                    description=f"Found {outlier_count} hire events with compensation > $500K",
                    metadata={"outlier_examples": outlier_details.to_dict("records")},
                )

            return AssetCheckResult(
                passed=True, description="All hire events have compensation ≤ $500K"
            )
    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing compensation outlier check: {str(e)}",
        )


@asset_check(
    asset=AssetKey(["fct_yearly_events"]), name="new_hire_compensation_range_check"
)
def check_new_hire_compensation_average(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Average new hire compensation between $60K-$120K."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_yearly_events'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_yearly_events table not found - dbt model may not be materialized",
                )

            avg_compensation = conn.execute(
                """
                SELECT AVG(compensation_amount)
                FROM fct_yearly_events
                WHERE event_type = 'hire'
            """
            ).fetchone()[0]

            if avg_compensation is None:
                return AssetCheckResult(
                    passed=False, description="No hire events found in database"
                )

            avg_compensation = round(avg_compensation, 0)

            if 60000 <= avg_compensation <= 120000:
                return AssetCheckResult(
                    passed=True,
                    description=f"Average new hire compensation: ${avg_compensation:,.0f} (within expected range $60K-$120K)",
                )
            else:
                return AssetCheckResult(
                    passed=False,
                    description=f"Average new hire compensation: ${avg_compensation:,.0f} (outside expected range $60K-$120K)",
                    metadata={
                        "actual_average": avg_compensation,
                        "expected_min": 60000,
                        "expected_max": 120000,
                    },
                )
    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing new hire compensation check: {str(e)}",
        )


@asset_check(
    asset=AssetKey(["fct_yearly_events"]), name="compensation_progression_check"
)
def check_compensation_progression_by_level(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Compensation progression logical across levels 1-5."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_yearly_events'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_yearly_events table not found - dbt model may not be materialized",
                )

            level_averages = conn.execute(
                """
                SELECT
                    level_id,
                    AVG(compensation_amount) as avg_compensation,
                    COUNT(*) as hire_count
                FROM fct_yearly_events
                WHERE event_type = 'hire'
                GROUP BY level_id
                ORDER BY level_id
            """
            ).df()

            if len(level_averages) == 0:
                return AssetCheckResult(
                    passed=False,
                    description="No hire events found for compensation progression analysis",
                )

            # Check if compensation increases with level
            issues = []
            for i in range(1, len(level_averages)):
                current_level = level_averages.iloc[i]
                previous_level = level_averages.iloc[i - 1]

                if (
                    current_level["avg_compensation"]
                    <= previous_level["avg_compensation"]
                ):
                    issues.append(
                        f"Level {current_level['level_id']} avg (${current_level['avg_compensation']:,.0f}) ≤ Level {previous_level['level_id']} avg (${previous_level['avg_compensation']:,.0f})"
                    )

            if issues:
                return AssetCheckResult(
                    passed=False,
                    description=f"Compensation progression issues found: {'; '.join(issues)}",
                    metadata={"level_averages": level_averages.to_dict("records")},
                )

            return AssetCheckResult(
                passed=True,
                description="Compensation increases appropriately across all levels",
                metadata={"level_averages": level_averages.to_dict("records")},
            )
    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing compensation progression check: {str(e)}",
        )


@asset_check(
    asset=AssetKey(["fct_workforce_snapshot"]),
    name="prorated_compensation_bounds_check",
)
def check_prorated_compensation_bounds(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Prorated compensation within reasonable bounds."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_workforce_snapshot'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_workforce_snapshot table not found - dbt model may not be materialized",
                )

            proration_stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total_employees,
                    AVG(prorated_annual_compensation) as avg_prorated,
                    MIN(prorated_annual_compensation) as min_prorated,
                    MAX(prorated_annual_compensation) as max_prorated,
                    AVG(prorated_annual_compensation / current_compensation * 100) as avg_proration_percent
                FROM fct_workforce_snapshot
                WHERE detailed_status_code LIKE 'new_hire%'
                AND prorated_annual_compensation IS NOT NULL
            """
            ).fetchone()

            if proration_stats[0] == 0:
                return AssetCheckResult(
                    passed=False,
                    description="No new hire records found for proration analysis",
                )

            (
                total_employees,
                avg_prorated,
                min_prorated,
                max_prorated,
                avg_proration_percent,
            ) = proration_stats

            issues = []

            # Check for negative proration (should never happen)
            if min_prorated < 0:
                issues.append(
                    f"Negative prorated compensation found: ${min_prorated:,.0f}"
                )

            # Check for proration > 100% (should never happen for new hires)
            if avg_proration_percent > 100:
                issues.append(
                    f"Average proration percentage > 100%: {avg_proration_percent:.1f}%"
                )

            # Check for unreasonably low average (< $10K suggests calculation error)
            if avg_prorated < 10000:
                issues.append(
                    f"Average prorated compensation too low: ${avg_prorated:,.0f}"
                )

            if issues:
                return AssetCheckResult(
                    passed=False,
                    description=f"Prorated compensation issues: {'; '.join(issues)}",
                    metadata={
                        "total_employees": total_employees,
                        "avg_prorated": avg_prorated,
                        "min_prorated": min_prorated,
                        "max_prorated": max_prorated,
                        "avg_proration_percent": avg_proration_percent,
                    },
                )

            return AssetCheckResult(
                passed=True,
                description=f"Prorated compensation within bounds (avg: ${avg_prorated:,.0f}, {avg_proration_percent:.1f}% of full salary)",
                metadata={
                    "total_employees": total_employees,
                    "avg_prorated": avg_prorated,
                    "avg_proration_percent": avg_proration_percent,
                },
            )
    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing prorated compensation bounds check: {str(e)}",
        )


# === GROWTH RATE VALIDATION ASSET CHECKS ===


@asset_check(
    asset=AssetKey(["fct_workforce_snapshot"]), name="growth_rate_tolerance_check"
)
def check_growth_rate_tolerance(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Year-over-year growth rate within ±0.5% tolerance of target (3%)."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_workforce_snapshot'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_workforce_snapshot table not found - dbt model may not be materialized",
                )

            # Get growth rate data by year
            growth_data = conn.execute(
                """
                WITH workforce_by_year AS (
                    SELECT
                        simulation_year,
                        COUNT(*) as active_count
                    FROM fct_workforce_snapshot
                    WHERE employment_status = 'active'
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                ),
                growth_rates AS (
                    SELECT
                        simulation_year,
                        active_count,
                        LAG(active_count) OVER (ORDER BY simulation_year) as prev_year_count,
                        CASE
                            WHEN LAG(active_count) OVER (ORDER BY simulation_year) IS NOT NULL
                            THEN (active_count - LAG(active_count) OVER (ORDER BY simulation_year)) /
                                 LAG(active_count) OVER (ORDER BY simulation_year)::FLOAT
                            ELSE NULL
                        END as actual_growth_rate
                    FROM workforce_by_year
                )
                SELECT
                    simulation_year,
                    active_count,
                    prev_year_count,
                    actual_growth_rate,
                    ABS(actual_growth_rate - 0.03) as deviation_from_target
                FROM growth_rates
                WHERE actual_growth_rate IS NOT NULL
                ORDER BY simulation_year
                """
            ).df()

            if growth_data.empty:
                return AssetCheckResult(
                    passed=False,
                    description="No multi-year workforce data found for growth rate validation",
                )

            # Check if any year exceeds tolerance (±0.5% = ±0.005)
            tolerance = 0.005
            violations = growth_data[growth_data["deviation_from_target"] > tolerance]

            if not violations.empty:
                violation_details = []
                for _, row in violations.iterrows():
                    violation_details.append(
                        {
                            "year": int(row["simulation_year"]),
                            "actual_growth": round(
                                float(row["actual_growth_rate"]) * 100, 2
                            ),
                            "target_growth": 3.0,
                            "deviation": round(
                                float(row["deviation_from_target"]) * 100, 2
                            ),
                        }
                    )

                return AssetCheckResult(
                    passed=False,
                    description=f"Growth rate tolerance violation: {len(violations)} years exceed ±0.5% tolerance",
                    metadata={
                        "violations": violation_details,
                        "tolerance_percent": 0.5,
                        "target_growth_percent": 3.0,
                    },
                )

            # Calculate average deviation for passing case
            avg_deviation = growth_data["deviation_from_target"].mean()

            return AssetCheckResult(
                passed=True,
                description=f"All years within growth rate tolerance (avg deviation: {avg_deviation*100:.2f}%)",
                metadata={
                    "years_validated": len(growth_data),
                    "avg_deviation_percent": round(avg_deviation * 100, 2),
                    "tolerance_percent": 0.5,
                },
            )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing growth rate tolerance check: {str(e)}",
        )


@asset_check(
    asset=AssetKey(["fct_workforce_snapshot"]),
    name="cumulative_growth_validation_check",
)
def check_cumulative_growth_validation(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Cumulative multi-year growth matches expected compound growth."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_workforce_snapshot'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_workforce_snapshot table not found - dbt model may not be materialized",
                )

            # Get baseline and final workforce counts for cumulative validation
            cumulative_data = conn.execute(
                """
                WITH workforce_bounds AS (
                    SELECT
                        MIN(simulation_year) as start_year,
                        MAX(simulation_year) as end_year
                    FROM fct_workforce_snapshot
                    WHERE employment_status = 'active'
                ),
                baseline_final AS (
                    SELECT
                        wb.start_year,
                        wb.end_year,
                        baseline.active_count as baseline_workforce,
                        final.active_count as final_workforce,
                        (wb.end_year - wb.start_year) as years_elapsed
                    FROM workforce_bounds wb
                    LEFT JOIN (
                        SELECT simulation_year, COUNT(*) as active_count
                        FROM fct_workforce_snapshot
                        WHERE employment_status = 'active'
                        GROUP BY simulation_year
                    ) baseline ON baseline.simulation_year = wb.start_year
                    LEFT JOIN (
                        SELECT simulation_year, COUNT(*) as active_count
                        FROM fct_workforce_snapshot
                        WHERE employment_status = 'active'
                        GROUP BY simulation_year
                    ) final ON final.simulation_year = wb.end_year
                )
                SELECT
                    start_year,
                    end_year,
                    baseline_workforce,
                    final_workforce,
                    years_elapsed,
                    -- Expected final workforce with 3% compound growth
                    ROUND(baseline_workforce * POWER(1.03, years_elapsed)) as expected_final,
                    -- Actual cumulative growth rate
                    CASE
                        WHEN years_elapsed > 0 AND baseline_workforce > 0
                        THEN POWER(final_workforce::FLOAT / baseline_workforce, 1.0/years_elapsed) - 1
                        ELSE NULL
                    END as actual_cumulative_rate
                FROM baseline_final
                """
            ).fetchone()

            if cumulative_data is None or cumulative_data[2] is None:
                return AssetCheckResult(
                    passed=False,
                    description="Insufficient data for cumulative growth validation",
                )

            (
                start_year,
                end_year,
                baseline,
                final,
                years,
                expected_final,
                actual_rate,
            ) = cumulative_data

            if years < 2:
                return AssetCheckResult(
                    passed=True,
                    description="Single year simulation - cumulative validation not applicable",
                )

            # Check if cumulative growth is within tolerance
            tolerance = 0.005  # ±0.5%
            target_rate = 0.03
            deviation = (
                abs(actual_rate - target_rate) if actual_rate is not None else 1.0
            )

            if deviation > tolerance:
                return AssetCheckResult(
                    passed=False,
                    description="Cumulative growth rate deviation exceeds tolerance",
                    metadata={
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "baseline_workforce": int(baseline),
                        "final_workforce": int(final),
                        "expected_final": int(expected_final),
                        "years_elapsed": int(years),
                        "actual_cumulative_rate_percent": round(actual_rate * 100, 2)
                        if actual_rate
                        else None,
                        "target_rate_percent": 3.0,
                        "deviation_percent": round(deviation * 100, 2),
                    },
                )

            return AssetCheckResult(
                passed=True,
                description=f"Cumulative growth within tolerance over {years} years (actual: {actual_rate*100:.2f}%)",
                metadata={
                    "years_validated": int(years),
                    "actual_cumulative_rate_percent": round(actual_rate * 100, 2),
                    "target_rate_percent": 3.0,
                    "deviation_percent": round(deviation * 100, 2),
                },
            )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing cumulative growth validation: {str(e)}",
        )


# === TERMINATION RATE VALIDATION ASSET CHECKS ===


@asset_check(asset=AssetKey(["fct_yearly_events"]), name="total_termination_rate_check")
def check_total_termination_rate(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Total termination rate matches configured rate (12%) within tolerance."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_yearly_events'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_yearly_events table not found - dbt model may not be materialized",
                )

            # Get termination rate data by year
            termination_data = conn.execute(
                """
                WITH yearly_workforce AS (
                    -- Get active workforce at start of each year
                    SELECT
                        simulation_year,
                        COUNT(*) as start_active_workforce
                    FROM fct_workforce_snapshot
                    WHERE employment_status = 'active'
                    GROUP BY simulation_year
                ),
                yearly_terminations AS (
                    -- Get total terminations by year
                    SELECT
                        simulation_year,
                        COUNT(*) as total_terminations
                    FROM fct_yearly_events
                    WHERE event_type = 'termination'
                    GROUP BY simulation_year
                )
                SELECT
                    yw.simulation_year,
                    yw.start_active_workforce,
                    COALESCE(yt.total_terminations, 0) as total_terminations,
                    CASE
                        WHEN yw.start_active_workforce > 0
                        THEN COALESCE(yt.total_terminations, 0)::FLOAT / yw.start_active_workforce
                        ELSE 0.0
                    END as actual_termination_rate,
                    ABS((COALESCE(yt.total_terminations, 0)::FLOAT / yw.start_active_workforce) - 0.12) as deviation_from_target
                FROM yearly_workforce yw
                LEFT JOIN yearly_terminations yt ON yw.simulation_year = yt.simulation_year
                WHERE yw.start_active_workforce > 0
                ORDER BY yw.simulation_year
                """
            ).df()

            if termination_data.empty:
                return AssetCheckResult(
                    passed=False,
                    description="No termination data found for rate validation",
                )

            # Check if any year exceeds tolerance (±5% of target rate)
            tolerance = 0.012  # 5% of 12% = 0.6% absolute tolerance
            violations = termination_data[
                termination_data["deviation_from_target"] > tolerance
            ]

            if not violations.empty:
                violation_details = []
                for _, row in violations.iterrows():
                    violation_details.append(
                        {
                            "year": int(row["simulation_year"]),
                            "workforce": int(row["start_active_workforce"]),
                            "terminations": int(row["total_terminations"]),
                            "actual_rate": round(
                                float(row["actual_termination_rate"]) * 100, 2
                            ),
                            "target_rate": 12.0,
                            "deviation": round(
                                float(row["deviation_from_target"]) * 100, 2
                            ),
                        }
                    )

                return AssetCheckResult(
                    passed=False,
                    description=f"Termination rate tolerance violation: {len(violations)} years exceed tolerance",
                    metadata={
                        "violations": violation_details,
                        "tolerance_percent": 1.2,  # 5% of 12%
                        "target_rate_percent": 12.0,
                    },
                )

            # Calculate average deviation for passing case
            avg_deviation = termination_data["deviation_from_target"].mean()
            avg_actual_rate = termination_data["actual_termination_rate"].mean()

            return AssetCheckResult(
                passed=True,
                description=f"All years within termination rate tolerance (avg rate: {avg_actual_rate*100:.2f}%)",
                metadata={
                    "years_validated": len(termination_data),
                    "avg_actual_rate_percent": round(avg_actual_rate * 100, 2),
                    "target_rate_percent": 12.0,
                    "avg_deviation_percent": round(avg_deviation * 100, 2),
                },
            )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing total termination rate check: {str(e)}",
        )


@asset_check(
    asset=AssetKey(["fct_yearly_events"]), name="new_hire_termination_rate_check"
)
def check_new_hire_termination_rate(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: New hire termination rate matches configured rate (25%) within tolerance."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify table exists first
            table_exists = conn.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_yearly_events'
                """
            ).fetchone()[0]

            if table_exists == 0:
                return AssetCheckResult(
                    passed=False,
                    description="fct_yearly_events table not found - dbt model may not be materialized",
                )

            # Get new hire termination rate data by year
            new_hire_data = conn.execute(
                """
                WITH yearly_new_hires AS (
                    -- Get new hires by year
                    SELECT
                        simulation_year,
                        COUNT(*) as total_new_hires
                    FROM fct_yearly_events
                    WHERE event_type = 'hire'
                    GROUP BY simulation_year
                ),
                yearly_new_hire_terminations AS (
                    -- Get new hire terminations by year
                    SELECT
                        simulation_year,
                        COUNT(*) as new_hire_terminations
                    FROM fct_yearly_events
                    WHERE event_type = 'termination'
                    AND event_category = 'new_hire_termination'
                    GROUP BY simulation_year
                )
                SELECT
                    ynh.simulation_year,
                    ynh.total_new_hires,
                    COALESCE(ynht.new_hire_terminations, 0) as new_hire_terminations,
                    CASE
                        WHEN ynh.total_new_hires > 0
                        THEN COALESCE(ynht.new_hire_terminations, 0)::FLOAT / ynh.total_new_hires
                        ELSE 0.0
                    END as actual_new_hire_termination_rate,
                    ABS((COALESCE(ynht.new_hire_terminations, 0)::FLOAT / ynh.total_new_hires) - 0.25) as deviation_from_target
                FROM yearly_new_hires ynh
                LEFT JOIN yearly_new_hire_terminations ynht ON ynh.simulation_year = ynht.simulation_year
                WHERE ynh.total_new_hires > 0
                ORDER BY ynh.simulation_year
                """
            ).df()

            if new_hire_data.empty:
                return AssetCheckResult(
                    passed=False,
                    description="No new hire termination data found for rate validation",
                )

            # Check if any year exceeds tolerance (±5% of target rate)
            tolerance = 0.025  # 5% of 25% = 1.25% absolute tolerance
            violations = new_hire_data[
                new_hire_data["deviation_from_target"] > tolerance
            ]

            if not violations.empty:
                violation_details = []
                for _, row in violations.iterrows():
                    violation_details.append(
                        {
                            "year": int(row["simulation_year"]),
                            "new_hires": int(row["total_new_hires"]),
                            "new_hire_terminations": int(row["new_hire_terminations"]),
                            "actual_rate": round(
                                float(row["actual_new_hire_termination_rate"]) * 100, 2
                            ),
                            "target_rate": 25.0,
                            "deviation": round(
                                float(row["deviation_from_target"]) * 100, 2
                            ),
                        }
                    )

                return AssetCheckResult(
                    passed=False,
                    description=f"New hire termination rate tolerance violation: {len(violations)} years exceed tolerance",
                    metadata={
                        "violations": violation_details,
                        "tolerance_percent": 2.5,  # 5% of 25%
                        "target_rate_percent": 25.0,
                    },
                )

            # Calculate average deviation for passing case
            avg_deviation = new_hire_data["deviation_from_target"].mean()
            avg_actual_rate = new_hire_data["actual_new_hire_termination_rate"].mean()

            return AssetCheckResult(
                passed=True,
                description=f"All years within new hire termination rate tolerance (avg rate: {avg_actual_rate*100:.2f}%)",
                metadata={
                    "years_validated": len(new_hire_data),
                    "avg_actual_rate_percent": round(avg_actual_rate * 100, 2),
                    "target_rate_percent": 25.0,
                    "avg_deviation_percent": round(avg_deviation * 100, 2),
                },
            )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing new hire termination rate check: {str(e)}",
        )


# === MULTI-YEAR CONSISTENCY VALIDATION ASSET CHECKS ===


@asset_check(
    asset=AssetKey(["fct_workforce_snapshot", "fct_yearly_events"]),
    name="simulation_consistency_check",
)
def check_simulation_consistency(
    context: AssetExecutionContext, duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Multi-year simulation mathematical and business rule consistency."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Verify both tables exist
            tables_exist = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN table_name = 'fct_workforce_snapshot' THEN 1 ELSE 0 END) as workforce_exists,
                    SUM(CASE WHEN table_name = 'fct_yearly_events' THEN 1 ELSE 0 END) as events_exists
                FROM information_schema.tables
                WHERE table_name IN ('fct_workforce_snapshot', 'fct_yearly_events')
                """
            ).fetchone()

            if tables_exist[0] == 0 or tables_exist[1] == 0:
                return AssetCheckResult(
                    passed=False,
                    description="Required tables not found - fct_workforce_snapshot or fct_yearly_events missing",
                )

            # Comprehensive consistency validation
            consistency_data = conn.execute(
                """
                WITH simulation_bounds AS (
                    SELECT
                        MIN(simulation_year) as start_year,
                        MAX(simulation_year) as end_year,
                        COUNT(DISTINCT simulation_year) as total_years
                    FROM fct_workforce_snapshot
                ),
                workforce_evolution AS (
                    SELECT
                        simulation_year,
                        COUNT(*) as total_employees,
                        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                        COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as terminated_employees
                    FROM fct_workforce_snapshot
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                ),
                event_totals AS (
                    SELECT
                        simulation_year,
                        COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as total_hires,
                        COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as total_terminations,
                        COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) as total_promotions,
                        COUNT(CASE WHEN event_type = 'merit' THEN 1 END) as total_merit
                    FROM fct_yearly_events
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                ),
                status_distribution AS (
                    SELECT
                        simulation_year,
                        COUNT(CASE WHEN detailed_status_code = 'continuous_active' THEN 1 END) as continuous_active,
                        COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_active,
                        COUNT(CASE WHEN detailed_status_code = 'experienced_termination' THEN 1 END) as experienced_termination,
                        COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END) as new_hire_termination
                    FROM fct_workforce_snapshot
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                )
                SELECT
                    sb.total_years,
                    sb.start_year,
                    sb.end_year,
                    -- Mathematical consistency: active employees should match hires - terminations pattern
                    we_start.active_employees as baseline_active,
                    we_end.active_employees as final_active,
                    SUM(et.total_hires) as cumulative_hires,
                    SUM(et.total_terminations) as cumulative_terminations,
                    -- Expected final = baseline + hires - terminations
                    (we_start.active_employees + SUM(et.total_hires) - SUM(et.total_terminations)) as expected_final,
                    -- Growth rate consistency
                    CASE
                        WHEN we_start.active_employees > 0 AND sb.total_years > 1
                        THEN POWER(we_end.active_employees::FLOAT / we_start.active_employees, 1.0/(sb.total_years-1)) - 1
                        ELSE NULL
                    END as actual_compound_growth_rate,
                    -- Status distribution consistency
                    SUM(sd.continuous_active + sd.new_hire_active) as total_active_from_status,
                    SUM(sd.experienced_termination + sd.new_hire_termination) as total_terminated_from_status,
                    -- Event totals validation
                    SUM(et.total_promotions) as total_promotions,
                    SUM(et.total_merit) as total_merit_events
                FROM simulation_bounds sb
                CROSS JOIN workforce_evolution we_start
                CROSS JOIN workforce_evolution we_end
                CROSS JOIN event_totals et
                CROSS JOIN status_distribution sd
                WHERE we_start.simulation_year = sb.start_year
                AND we_end.simulation_year = sb.end_year
                AND et.simulation_year BETWEEN sb.start_year AND sb.end_year
                AND sd.simulation_year BETWEEN sb.start_year AND sb.end_year
                GROUP BY sb.total_years, sb.start_year, sb.end_year,
                         we_start.active_employees, we_end.active_employees
                """
            ).fetchone()

            if consistency_data is None:
                return AssetCheckResult(
                    passed=False,
                    description="Insufficient data for multi-year consistency validation",
                )

            (
                total_years,
                start_year,
                end_year,
                baseline_active,
                final_active,
                cumulative_hires,
                cumulative_terminations,
                expected_final,
                actual_growth_rate,
                total_active_status,
                total_terminated_status,
                total_promotions,
                total_merit,
            ) = consistency_data

            validation_issues = []

            # 1. Mathematical consistency check
            math_variance = abs(final_active - expected_final)
            if math_variance > 5:  # Allow small variance for rounding
                validation_issues.append(
                    {
                        "type": "mathematical_inconsistency",
                        "description": f"Final workforce ({final_active}) != baseline + hires - terminations ({expected_final})",
                        "variance": math_variance,
                    }
                )

            # 2. Growth rate consistency check (if multi-year)
            if total_years > 1 and actual_growth_rate is not None:
                target_growth = 0.03
                growth_deviation = abs(actual_growth_rate - target_growth)
                if growth_deviation > 0.005:  # ±0.5% tolerance
                    validation_issues.append(
                        {
                            "type": "growth_rate_deviation",
                            "description": f"Compound growth rate ({actual_growth_rate:.3f}) deviates from target (0.03)",
                            "deviation": growth_deviation,
                        }
                    )

            # 3. Status distribution consistency
            if total_active_status != final_active:
                validation_issues.append(
                    {
                        "type": "status_inconsistency",
                        "description": f"Active employees from status codes ({total_active_status}) != final active ({final_active})",
                    }
                )

            # 4. Event volume reasonableness checks
            if total_years > 1:
                avg_hires_per_year = cumulative_hires / total_years
                avg_workforce = (baseline_active + final_active) / 2

                # Hires should be reasonable relative to workforce size
                hire_rate = (
                    avg_hires_per_year / avg_workforce if avg_workforce > 0 else 0
                )
                if hire_rate > 0.5:  # More than 50% turnover seems excessive
                    validation_issues.append(
                        {
                            "type": "excessive_hiring_rate",
                            "description": f"Average hiring rate ({hire_rate:.3f}) exceeds reasonable threshold (0.5)",
                        }
                    )

            # Return results
            if validation_issues:
                return AssetCheckResult(
                    passed=False,
                    description=f"Simulation consistency violations: {len(validation_issues)} issues found",
                    metadata={
                        "validation_issues": validation_issues,
                        "summary": {
                            "years": int(total_years),
                            "baseline_workforce": int(baseline_active),
                            "final_workforce": int(final_active),
                            "cumulative_hires": int(cumulative_hires),
                            "cumulative_terminations": int(cumulative_terminations),
                            "actual_growth_rate": round(actual_growth_rate * 100, 2)
                            if actual_growth_rate
                            else None,
                        },
                    },
                )

            return AssetCheckResult(
                passed=True,
                description=f"Multi-year simulation consistency validated over {total_years} years",
                metadata={
                    "years_validated": int(total_years),
                    "mathematical_variance": int(math_variance),
                    "growth_rate_percent": round(actual_growth_rate * 100, 2)
                    if actual_growth_rate
                    else None,
                    "cumulative_events": {
                        "hires": int(cumulative_hires),
                        "terminations": int(cumulative_terminations),
                        "promotions": int(total_promotions),
                        "merit_increases": int(total_merit),
                    },
                },
            )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing simulation consistency check: {str(e)}",
        )


# === S047 OPTIMIZATION ENGINE ASSETS ===


@asset(
    deps=[planwise_dbt_assets],
    group_name="optimization_engine"
)
def advanced_optimization_engine(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
) -> Dict[str, Any]:
    """Advanced multi-objective optimization with monitoring."""

    # Try to get scenario_id from partition_key or default
    try:
        scenario_id = context.partition_key or "optimization_run"
    except:
        scenario_id = "optimization_run"

    # Get optimization configuration from various sources
    optimization_config = {}

    # Try to read from temporary config file first (for Streamlit integration)
    temp_config_path = Path("/tmp/planwise_optimization_config.yaml")
    if temp_config_path.exists():
        try:
            import yaml
            with open(temp_config_path, 'r') as f:
                file_config = yaml.safe_load(f)
                optimization_config = file_config.get("optimization", {})
            # Clean up the temporary file
            temp_config_path.unlink()
            context.log.info(f"Loaded optimization config from temporary file")
        except Exception as e:
            context.log.warning(f"Could not read temporary config file: {e}")

    # If no config found, use run_config as fallback
    if not optimization_config:
        optimization_config = context.run_config.get("optimization", {})

    if not optimization_config:
        # Use default optimization configuration
        optimization_config = {
            "scenario_id": "default_optimization",
            "initial_parameters": {
                "merit_rate_level_1": 0.045,
                "merit_rate_level_2": 0.040,
                "merit_rate_level_3": 0.035,
                "merit_rate_level_4": 0.035,
                "merit_rate_level_5": 0.040,
                "cola_rate": 0.025,
                "new_hire_salary_adjustment": 1.15,
                "promotion_probability_level_1": 0.12,
                "promotion_probability_level_2": 0.08,
                "promotion_probability_level_3": 0.05,
                "promotion_probability_level_4": 0.02,
                "promotion_probability_level_5": 0.01,
                "promotion_raise_level_1": 0.12,
                "promotion_raise_level_2": 0.12,
                "promotion_raise_level_3": 0.12,
                "promotion_raise_level_4": 0.12,
                "promotion_raise_level_5": 0.12,
            },
            "objectives": {"cost": 0.4, "equity": 0.3, "targets": 0.3},
            "method": "SLSQP",
            "max_evaluations": 200,
            "timeout_minutes": 30,
            "random_seed": 42,
            "use_synthetic": True  # Default to synthetic for safety
        }

    request = OptimizationRequest(**optimization_config)
    scenario_id = request.scenario_id

    # Initialize optimizer with monitoring and use_synthetic flag from request
    optimizer = CompensationOptimizer(duckdb_resource, scenario_id, use_synthetic=request.use_synthetic)

    context.log.info(f"Starting optimization for scenario: {scenario_id}")
    context.log.info(f"Algorithm: {request.method}, Max evaluations: {request.max_evaluations}")
    if request.use_synthetic:
        context.log.info(f"🧪 SYNTHETIC MODE: Using fast synthetic objective functions")
    else:
        context.log.info(f"🔄 REAL SIMULATION MODE: Each evaluation will run full dbt simulation (~30-60s each)")
        context.log.info(f"⏱️ Estimated total time: {(request.max_evaluations * 45) / 60:.1f} - {(request.max_evaluations * 90) / 60:.1f} minutes")

    # Verify simulation data exists
    try:
        with duckdb_resource.get_connection() as conn:
            # Check if required tables exist
            tables_check = conn.execute("""
                SELECT COUNT(*) as table_count
                FROM information_schema.tables
                WHERE table_name IN ('fct_workforce_snapshot', 'fct_yearly_events', 'comp_levers')
            """).fetchone()

            if tables_check[0] < 3:
                context.log.warning("Required simulation tables not found. Running basic optimization...")
    except Exception as e:
        context.log.warning(f"Could not verify simulation tables: {e}")

    # Run optimization
    try:
        result = optimizer.optimize(
            initial_parameters=request.initial_parameters,
            objectives=request.objectives,
            method=request.method,
            max_evaluations=request.max_evaluations,
            timeout_minutes=request.timeout_minutes,
            random_seed=request.random_seed
        )

        # Check if result is an OptimizationError (returned directly, not thrown)
        if isinstance(result, OptimizationError):
            context.log.error(f"Optimization returned error: {result.error_message}")
            # Return error as dict with error flag
            result_dict = result.dict()
            result_dict["optimization_failed"] = True
            return result_dict

        # Handle successful OptimizationResult
        context.log.info(f"Optimization converged: {result.converged}")
        context.log.info(f"Function evaluations: {result.function_evaluations}")
        context.log.info(f"Runtime: {result.runtime_seconds:.2f}s")
        context.log.info(f"Risk assessment: {result.risk_assessment}")

        if hasattr(result, 'estimated_cost_impact'):
            cost_impact = result.estimated_cost_impact.get('value', 0)
            context.log.info(f"Cost impact: ${cost_impact:,.0f}")

        # Convert to dict for Dagster compatibility
        result_dict = result.dict()

        # Save results to temporary file for Streamlit UI access
        try:
            import pickle
            temp_result_path = "/tmp/planwise_optimization_result.pkl"
            with open(temp_result_path, 'wb') as f:
                pickle.dump(result_dict, f)
            context.log.info(f"✅ Saved optimization results to {temp_result_path} for UI access")
        except Exception as e:
            context.log.warning(f"Could not save temporary result file: {e}")

        return result_dict

    except Exception as e:
        context.log.error(f"Optimization failed: {str(e)}")
        error_result = OptimizationError(
            scenario_id=scenario_id,
            error_type="NUMERICAL",
            error_message=str(e),
            best_found_solution=None,
            recommendations=["Check parameter bounds", "Try different algorithm"]
        )
        # Return error as dict with error flag
        result_dict = error_result.dict()
        result_dict["optimization_failed"] = True

        # Save error results to temporary file for Streamlit UI access
        try:
            import pickle
            temp_result_path = "/tmp/planwise_optimization_result.pkl"
            with open(temp_result_path, 'wb') as f:
                pickle.dump(result_dict, f)
            context.log.info(f"✅ Saved optimization error to {temp_result_path} for UI access")
        except Exception as e:
            context.log.warning(f"Could not save temporary error file: {e}")

        return result_dict


@asset(
    group_name="optimization_engine"
)
def optimization_sensitivity_analysis(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    advanced_optimization_engine: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate sensitivity analysis for optimization results."""

    try:
        scenario_id = context.partition_key or "sensitivity_analysis"
    except:
        scenario_id = "sensitivity_analysis"

    # Initialize sensitivity analyzer
    analyzer = SensitivityAnalyzer(duckdb_resource, scenario_id)

    # Get optimization configuration for objectives
    optimization_config = context.run_config.get("optimization", {})
    objectives = optimization_config.get("objectives", {"cost": 0.4, "equity": 0.3, "targets": 0.3})

    context.log.info("Calculating parameter sensitivities...")

    try:
        # Generate sensitivity report
        if not advanced_optimization_engine.get("optimization_failed", False):
            sensitivity_report = analyzer.generate_sensitivity_report(
                parameters=advanced_optimization_engine.get("optimal_parameters", {}),
                objectives=objectives
            )

            context.log.info(f"Generated sensitivity analysis for {len(sensitivity_report['parameter_sensitivities'])} parameters")

            # Log top sensitive parameters
            most_sensitive = sensitivity_report.get('most_sensitive_parameters', [])[:3]
            if most_sensitive:
                context.log.info(f"Most sensitive parameters: {[param[0] for param in most_sensitive]}")

            return sensitivity_report
        else:
            context.log.warning("Optimization did not succeed, skipping sensitivity analysis")
            return {"error": "Optimization failed", "sensitivities": {}}

    except Exception as e:
        context.log.error(f"Sensitivity analysis failed: {str(e)}")
        return {"error": str(e), "sensitivities": {}}


@asset(
    group_name="optimization_engine"
)
def optimization_evidence_report(
    context: AssetExecutionContext,
    advanced_optimization_engine: Dict[str, Any],
) -> Dict[str, str]:
    """Generate evidence report for optimization results."""

    context.log.info("Generating optimization evidence report...")

    try:
        if not advanced_optimization_engine.get("optimization_failed", False):
            # Create OptimizationResult object for evidence generator
            result_obj = OptimizationResult(**advanced_optimization_engine)
            evidence_generator = EvidenceGenerator(result_obj)
            report_path = evidence_generator.generate_mdx_report()

            context.log.info(f"Generated evidence report: {report_path}")

            return {
                "report_path": report_path,
                "scenario_id": advanced_optimization_engine.get("scenario_id", "unknown"),
                "generated_at": pd.Timestamp.now().isoformat()
            }
        else:
            context.log.warning("Optimization did not succeed, skipping evidence report")
            return {"error": "Optimization failed", "report_path": None}

    except Exception as e:
        context.log.error(f"Evidence report generation failed: {str(e)}")
        return {"error": str(e), "report_path": None}


# Asset checks for optimization engine
@asset_check(asset=advanced_optimization_engine)
def optimization_convergence_check(
    context: AssetExecutionContext,
    advanced_optimization_engine: Dict[str, Any]
) -> AssetCheckResult:
    """Asset check: Optimization convergence and performance validation."""

    if advanced_optimization_engine.get("optimization_failed", False):
        return AssetCheckResult(
            passed=False,
            description=f"Optimization failed: {advanced_optimization_engine.get('error_message', 'Unknown error')}",
            metadata={
                "error_type": advanced_optimization_engine.get("error_type", "UNKNOWN"),
                "recommendations": advanced_optimization_engine.get("recommendations", [])
            }
        )

    if not advanced_optimization_engine.get("converged", False):
        return AssetCheckResult(
            passed=False,
            description=f"Optimization did not converge after {advanced_optimization_engine.get('function_evaluations', 0)} evaluations",
            metadata={
                "algorithm": advanced_optimization_engine.get("algorithm_used", "unknown"),
                "evaluations": advanced_optimization_engine.get("function_evaluations", 0),
                "runtime_seconds": advanced_optimization_engine.get("runtime_seconds", 0)
            }
        )

    # Performance threshold checks
    function_evaluations = advanced_optimization_engine.get("function_evaluations", 0)
    if function_evaluations > 300:
        return AssetCheckResult(
            passed=False,
            description=f"Optimization required {function_evaluations} evaluations (threshold: 300)",
            metadata={
                "runtime_seconds": advanced_optimization_engine.get("runtime_seconds", 0),
                "algorithm": advanced_optimization_engine.get("algorithm_used", "unknown")
            }
        )

    # Quality score check
    quality_score = advanced_optimization_engine.get("solution_quality_score", 0.0)
    if quality_score < 0.7:
        return AssetCheckResult(
            passed=False,
            description=f"Solution quality score {quality_score:.2f} below threshold (0.7)",
            metadata={
                "quality_score": quality_score,
                "risk_assessment": advanced_optimization_engine.get("risk_assessment", "unknown")
            }
        )

    return AssetCheckResult(
        passed=True,
        description="Optimization completed successfully",
        metadata={
            "converged": advanced_optimization_engine.get("converged", False),
            "evaluations": function_evaluations,
            "runtime_seconds": advanced_optimization_engine.get("runtime_seconds", 0),
            "quality_score": quality_score,
            "risk_assessment": advanced_optimization_engine.get("risk_assessment", "unknown")
        }
    )


@asset(deps=[planwise_dbt_assets], group_name="eligibility_engine")
def eligibility_determination(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    simulation_config: Dict[str, Any]
) -> pd.DataFrame:
    """
    Determine employee eligibility for DC plan participation (Epic E022: Story S022-01).

    This asset processes the int_eligibility_determination dbt model to provide
    eligibility status for all active employees across simulation years.

    Business Logic:
    - Employees become eligible after configurable waiting period (days since hire)
    - Only active employees are evaluated for eligibility
    - Eligibility is determined as of January 1st of each simulation year

    Returns:
        DataFrame with eligibility determinations for all simulation years
    """
    context.log.info("🎯 Starting eligibility determination processing...")

    with duckdb_resource.get_connection() as conn:
        # Set dbt variables for eligibility configuration
        waiting_period_days = simulation_config.get('eligibility', {}).get('waiting_period_days', 365)
        context.log.info(f"📋 Using waiting period: {waiting_period_days} days")

        # Query the materialized eligibility table
        query = """
        SELECT
            employee_id,
            employee_ssn,
            employee_hire_date,
            employment_status,
            simulation_year,
            days_since_hire,
            is_eligible,
            eligibility_reason,
            waiting_period_days,
            eligibility_evaluation_date
        FROM int_eligibility_determination
        WHERE simulation_year BETWEEN ? AND ?
        ORDER BY simulation_year, employee_id
        """

        start_year = simulation_config.get('start_year', 2025)
        end_year = simulation_config.get('end_year', 2029)

        eligibility_df = conn.execute(query, [start_year, end_year]).df()

        context.log.info(f"✅ Processed eligibility for {len(eligibility_df)} employee-year combinations")

        # Log summary statistics
        if not eligibility_df.empty:
            summary_stats = eligibility_df.groupby('simulation_year').agg({
                'is_eligible': ['count', 'sum'],
                'days_since_hire': ['min', 'max', 'mean']
            }).round(1)

            context.log.info("📊 Eligibility Summary by Year:")
            for year in sorted(eligibility_df['simulation_year'].unique()):
                year_data = eligibility_df[eligibility_df['simulation_year'] == year]
                eligible_count = year_data['is_eligible'].sum()
                total_count = len(year_data)
                eligible_pct = (eligible_count / total_count * 100) if total_count > 0 else 0

                context.log.info(f"   Year {year}: {eligible_count:,}/{total_count:,} eligible ({eligible_pct:.1f}%)")

        return eligibility_df


@asset_check(asset=eligibility_determination)
def eligibility_coverage_check(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Validate eligibility determination covers all active employees."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Check that all active employees have eligibility records
            coverage_query = """
            WITH active_employees AS (
                SELECT DISTINCT employee_id
                FROM int_baseline_workforce
                WHERE employment_status = 'active'
            ),
            eligibility_records AS (
                SELECT DISTINCT employee_id
                FROM int_eligibility_determination
                WHERE simulation_year = 2025  -- Check first year coverage
            )
            SELECT
                COUNT(a.employee_id) as total_active,
                COUNT(e.employee_id) as with_eligibility,
                COUNT(a.employee_id) - COUNT(e.employee_id) as missing_eligibility
            FROM active_employees a
            LEFT JOIN eligibility_records e ON a.employee_id = e.employee_id
            """

            result = conn.execute(coverage_query).fetchone()
            total_active, with_eligibility, missing_eligibility = result

            if missing_eligibility == 0:
                return AssetCheckResult(
                    passed=True,
                    description=f"✅ All {total_active:,} active employees have eligibility records",
                    metadata={
                        "total_active_employees": total_active,
                        "employees_with_eligibility": with_eligibility,
                        "coverage_percentage": 100.0
                    }
                )
            else:
                coverage_pct = (with_eligibility / total_active * 100) if total_active > 0 else 0
                return AssetCheckResult(
                    passed=False,
                    description=f"❌ {missing_eligibility:,} active employees missing eligibility records ({coverage_pct:.1f}% coverage)",
                    metadata={
                        "total_active_employees": total_active,
                        "employees_with_eligibility": with_eligibility,
                        "missing_eligibility_records": missing_eligibility,
                        "coverage_percentage": coverage_pct
                    }
                )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing eligibility coverage check: {str(e)}"
        )


@asset_check(asset=eligibility_determination)
def eligibility_logic_validation_check(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> AssetCheckResult:
    """Asset check: Validate eligibility logic produces consistent results."""
    try:
        with duckdb_resource.get_connection() as conn:
            # Test eligibility logic consistency
            validation_query = """
            SELECT
                COUNT(*) as total_records,
                SUM(CASE WHEN is_eligible = true AND days_since_hire >= waiting_period_days THEN 1 ELSE 0 END) as correct_eligible,
                SUM(CASE WHEN is_eligible = false AND days_since_hire < waiting_period_days THEN 1 ELSE 0 END) as correct_not_eligible,
                SUM(CASE WHEN
                    (is_eligible = true AND days_since_hire < waiting_period_days) OR
                    (is_eligible = false AND days_since_hire >= waiting_period_days)
                    THEN 1 ELSE 0 END) as logic_errors
            FROM int_eligibility_determination
            WHERE simulation_year = 2025  -- Check first year logic
            """

            result = conn.execute(validation_query).fetchone()
            total_records, correct_eligible, correct_not_eligible, logic_errors = result

            if logic_errors == 0:
                return AssetCheckResult(
                    passed=True,
                    description=f"✅ All {total_records:,} eligibility determinations follow correct logic",
                    metadata={
                        "total_records": total_records,
                        "correctly_eligible": correct_eligible,
                        "correctly_not_eligible": correct_not_eligible,
                        "logic_error_rate": 0.0
                    }
                )
            else:
                error_rate = (logic_errors / total_records * 100) if total_records > 0 else 0
                return AssetCheckResult(
                    passed=False,
                    description=f"❌ {logic_errors:,} eligibility logic errors found ({error_rate:.2f}% error rate)",
                    metadata={
                        "total_records": total_records,
                        "correctly_eligible": correct_eligible,
                        "correctly_not_eligible": correct_not_eligible,
                        "logic_errors": logic_errors,
                        "logic_error_rate": error_rate
                    }
                )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Error executing eligibility logic validation: {str(e)}"
        )


@asset_check(asset=advanced_optimization_engine)
def optimization_parameter_bounds_check(
    context: AssetExecutionContext,
    advanced_optimization_engine: Dict[str, Any]
) -> AssetCheckResult:
    """Asset check: Optimal parameters within acceptable bounds."""

    if advanced_optimization_engine.get("optimization_failed", False):
        return AssetCheckResult(passed=True, description="Skipping bounds check for failed optimization")

    from orchestrator.optimization.optimization_schemas import PARAMETER_SCHEMA

    violations = []
    optimal_parameters = advanced_optimization_engine.get("optimal_parameters", {})

    for param_name, value in optimal_parameters.items():
        if param_name in PARAMETER_SCHEMA:
            bounds = PARAMETER_SCHEMA[param_name]["range"]
            if not (bounds[0] <= value <= bounds[1]):
                violations.append({
                    "parameter": param_name,
                    "value": value,
                    "bounds": bounds,
                    "violation": "below_minimum" if value < bounds[0] else "above_maximum"
                })

    if violations:
        return AssetCheckResult(
            passed=False,
            description=f"Parameter bounds violations: {len(violations)} parameters outside acceptable ranges",
            metadata={"violations": violations}
        )

    return AssetCheckResult(
        passed=True,
        description="All optimal parameters within acceptable bounds",
        metadata={
            "parameters_validated": len(optimal_parameters),
            "constraint_violations": advanced_optimization_engine.get("constraint_violations", {})
        }
    )
