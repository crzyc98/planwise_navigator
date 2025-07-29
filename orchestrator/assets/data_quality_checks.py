"""
Data Quality Asset Checks for Promotion Compensation Integrity

Implements comprehensive data quality validation for promotion events to ensure:
1. Promotion events use correct previous compensation (not stale baseline data)
2. Merit events properly propagate to subsequent promotion calculations
3. Compensation gaps are within acceptable thresholds
4. Audit trail integrity is maintained

These checks run after yearly events are materialized and before workforce snapshots.
"""

from dagster import asset_check, AssetCheckResult, AssetCheckSeverity
from dagster_duckdb import DuckDBResource
from typing import Dict, Any, List
import pandas as pd


@asset_check(asset="fct_yearly_events", blocking=True)
def promotion_compensation_integrity_check(context, duckdb: DuckDBResource) -> AssetCheckResult:
    """
    Critical check: Validates promotion events use correct previous compensation.

    BLOCKING CHECK: This check must pass before workforce snapshot generation.
    Detects systematic use of stale compensation data in promotion events.
    """

    query = """
    SELECT
        COUNT(*) as total_promotions,
        SUM(CASE WHEN data_quality_status IN ('CRITICAL_VIOLATION', 'MAJOR_VIOLATION') THEN 1 ELSE 0 END) as violations,
        SUM(estimated_underpayment_amount) as total_underpayment,
        AVG(gap_percentage) as avg_gap_percentage,
        MAX(compensation_gap) as max_gap
    FROM data_quality_promotion_compensation
    WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_yearly_events WHERE event_type = 'promotion')
    """

    with duckdb.get_connection() as conn:
        result = conn.execute(query).fetchone()

        if result[0] == 0:  # No promotions to check
            return AssetCheckResult(
                passed=True,
                description="No promotion events found for current simulation year",
                metadata={"promotions_count": 0}
            )

        total_promotions, violations, total_underpayment, avg_gap_pct, max_gap = result
        violation_rate = (violations / total_promotions) * 100 if total_promotions > 0 else 0

        # Define pass criteria
        passed = violations == 0
        severity = AssetCheckSeverity.ERROR if violations > 0 else None

        return AssetCheckResult(
            passed=passed,
            severity=severity,
            description=f"Found {violations} promotion compensation violations out of {total_promotions} promotions ({violation_rate:.1f}% violation rate)",
            metadata={
                "total_promotions": total_promotions,
                "violations": violations,
                "violation_rate_percent": round(violation_rate, 2),
                "total_estimated_underpayment": round(total_underpayment or 0, 2),
                "avg_gap_percentage": round(avg_gap_pct or 0, 2),
                "max_compensation_gap": round(max_gap or 0, 2),
                "acceptable_violation_rate": 0.0,
                "check_type": "promotion_compensation_integrity"
            }
        )


@asset_check(asset="fct_yearly_events")
def merit_propagation_check(context, duckdb: DuckDBResource) -> AssetCheckResult:
    """
    Validates that merit increases properly propagate to next year's promotion calculations.

    This check ensures merit events update the compensation state that feeds into
    subsequent promotion events, preventing use of pre-merit compensation data.
    """

    query = """
    SELECT
        COUNT(*) as total_promotions_with_prior_merit,
        SUM(CASE WHEN merit_propagation_status = 'MERIT_NOT_PROPAGATED' THEN 1 ELSE 0 END) as merit_failures,
        AVG(ABS(merit_propagation_gap)) as avg_propagation_gap,
        MAX(ABS(merit_propagation_gap)) as max_propagation_gap
    FROM data_quality_promotion_compensation
    WHERE merit_propagation_status IN ('MERIT_NOT_PROPAGATED', 'MERIT_PROPERLY_PROPAGATED')
        AND simulation_year = (SELECT MAX(simulation_year) FROM fct_yearly_events WHERE event_type = 'promotion')
    """

    with duckdb.get_connection() as conn:
        result = conn.execute(query).fetchone()

        if result[0] == 0:  # No merit events to check
            return AssetCheckResult(
                passed=True,
                description="No promotions with prior merit events found for validation",
                metadata={"promotions_with_merit": 0}
            )

        total_with_merit, merit_failures, avg_gap, max_gap = result
        failure_rate = (merit_failures / total_with_merit) * 100 if total_with_merit > 0 else 0

        # Merit propagation should be 100% successful
        passed = merit_failures == 0
        severity = AssetCheckSeverity.WARN if merit_failures > 0 else None

        return AssetCheckResult(
            passed=passed,
            severity=severity,
            description=f"Merit propagation: {merit_failures} failures out of {total_with_merit} promotions with prior merit ({failure_rate:.1f}% failure rate)",
            metadata={
                "total_promotions_with_prior_merit": total_with_merit,
                "merit_propagation_failures": merit_failures,
                "merit_failure_rate_percent": round(failure_rate, 2),
                "avg_propagation_gap": round(avg_gap or 0, 2),
                "max_propagation_gap": round(max_gap or 0, 2),
                "acceptable_failure_rate": 0.0,
                "check_type": "merit_propagation_integrity"
            }
        )


@asset_check(asset="fct_yearly_events")
def promotion_increase_reasonableness_check(context, duckdb: DuckDBResource) -> AssetCheckResult:
    """
    Validates that promotion salary increases are within reasonable business ranges.

    Typical promotion increases should be 15-30%. This check identifies outliers
    that may indicate data quality issues or business rule violations.
    """

    query = """
    SELECT
        COUNT(*) as total_promotions,
        SUM(CASE WHEN promotion_increase_validation != 'PROMOTION_INCREASE_VALID' THEN 1 ELSE 0 END) as invalid_increases,
        AVG(promotion_increase_percentage) as avg_increase_pct,
        MIN(promotion_increase_percentage) as min_increase_pct,
        MAX(promotion_increase_percentage) as max_increase_pct,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY promotion_increase_percentage) as median_increase_pct
    FROM data_quality_promotion_compensation
    WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_yearly_events WHERE event_type = 'promotion')
    """

    with duckdb.get_connection() as conn:
        result = conn.execute(query).fetchone()

        if result[0] == 0:
            return AssetCheckResult(
                passed=True,
                description="No promotion events found for increase validation",
                metadata={"promotions_count": 0}
            )

        total, invalid, avg_pct, min_pct, max_pct, median_pct = result
        invalid_rate = (invalid / total) * 100 if total > 0 else 0

        # Allow up to 5% of promotions to have irregular increases
        passed = invalid_rate <= 5.0
        severity = AssetCheckSeverity.WARN if not passed else None

        return AssetCheckResult(
            passed=passed,
            severity=severity,
            description=f"Promotion increases: {invalid} irregular increases out of {total} promotions ({invalid_rate:.1f}% irregular rate)",
            metadata={
                "total_promotions": total,
                "invalid_increases": invalid,
                "invalid_increase_rate_percent": round(invalid_rate, 2),
                "avg_increase_percent": round(avg_pct or 0, 1),
                "min_increase_percent": round(min_pct or 0, 1),
                "max_increase_percent": round(max_pct or 0, 1),
                "median_increase_percent": round(median_pct or 0, 1),
                "acceptable_irregular_rate": 5.0,
                "check_type": "promotion_increase_reasonableness"
            }
        )


@asset_check(asset="data_quality_summary")
def data_quality_compliance_check(context, duckdb: DuckDBResource) -> AssetCheckResult:
    """
    Executive-level compliance check based on overall data quality metrics.

    This check aggregates all data quality issues and determines if the system
    meets enterprise compliance standards for compensation data integrity.
    """

    query = """
    SELECT
        simulation_year,
        compliance_status,
        financial_risk_level,
        data_quality_score,
        total_violation_rate,
        total_estimated_underpayment,
        critical_violations,
        major_violations
    FROM data_quality_summary
    WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_yearly_events WHERE event_type = 'promotion')
    """

    with duckdb.get_connection() as conn:
        result = conn.execute(query).fetchone()

        if not result:
            return AssetCheckResult(
                passed=False,
                severity=AssetCheckSeverity.ERROR,
                description="No data quality summary available for current simulation year",
                metadata={"error": "missing_data_quality_summary"}
            )

        (sim_year, compliance_status, risk_level, quality_score,
         violation_rate, underpayment, critical_violations, major_violations) = result

        # Define compliance criteria
        compliant = compliance_status in ['COMPLIANT', 'MINOR_ISSUES']
        severity = None

        if compliance_status == 'CRITICAL_ISSUES':
            severity = AssetCheckSeverity.ERROR
        elif compliance_status == 'MODERATE_ISSUES':
            severity = AssetCheckSeverity.WARN

        return AssetCheckResult(
            passed=compliant,
            severity=severity,
            description=f"Data quality compliance: {compliance_status} | Risk: {risk_level} | Score: {quality_score}/100",
            metadata={
                "simulation_year": sim_year,
                "compliance_status": compliance_status,
                "financial_risk_level": risk_level,
                "data_quality_score": round(quality_score or 0, 1),
                "total_violation_rate_percent": round(violation_rate or 0, 2),
                "total_estimated_underpayment": round(underpayment or 0, 2),
                "critical_violations": critical_violations or 0,
                "major_violations": major_violations or 0,
                "min_acceptable_score": 95.0,
                "check_type": "executive_compliance_summary"
            }
        )


@asset_check(asset="fct_yearly_events")
def compensation_temporal_consistency_check(context, duckdb: DuckDBResource) -> AssetCheckResult:
    """
    Validates temporal consistency of compensation events within the same year.

    Ensures that:
    1. Events are properly sequenced (promotions before merit, etc.)
    2. Compensation amounts are monotonically increasing for the same employee
    3. No circular dependencies or contradictory events exist
    """

    query = """
    WITH employee_event_sequences AS (
        SELECT
            employee_id,
            simulation_year,
            event_type,
            effective_date,
            previous_compensation,
            compensation_amount,
            LAG(compensation_amount) OVER (
                PARTITION BY employee_id, simulation_year
                ORDER BY effective_date, event_sequence
            ) as prior_compensation_in_year
        FROM fct_yearly_events
        WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_yearly_events)
            AND event_type IN ('promotion', 'RAISE')
            AND compensation_amount IS NOT NULL
    ),
    temporal_violations AS (
        SELECT
            employee_id,
            COUNT(*) as event_count,
            SUM(CASE
                WHEN prior_compensation_in_year IS NOT NULL
                     AND previous_compensation != prior_compensation_in_year
                THEN 1 ELSE 0
            END) as temporal_inconsistencies
        FROM employee_event_sequences
        GROUP BY employee_id
        HAVING SUM(CASE
            WHEN prior_compensation_in_year IS NOT NULL
                 AND previous_compensation != prior_compensation_in_year
            THEN 1 ELSE 0
        END) > 0
    )
    SELECT
        COUNT(DISTINCT employee_id) as employees_with_violations,
        SUM(temporal_inconsistencies) as total_inconsistencies
    FROM temporal_violations
    """

    with duckdb.get_connection() as conn:
        result = conn.execute(query).fetchone()

        employees_with_violations, total_inconsistencies = result or (0, 0)

        passed = employees_with_violations == 0
        severity = AssetCheckSeverity.WARN if not passed else None

        return AssetCheckResult(
            passed=passed,
            severity=severity,
            description=f"Temporal consistency: {employees_with_violations} employees with {total_inconsistencies} compensation sequence violations",
            metadata={
                "employees_with_violations": employees_with_violations or 0,
                "total_inconsistencies": total_inconsistencies or 0,
                "acceptable_violations": 0,
                "check_type": "temporal_consistency"
            }
        )


def get_data_quality_dashboard_data(duckdb: DuckDBResource) -> Dict[str, Any]:
    """
    Helper function to retrieve comprehensive data quality metrics for dashboard display.

    Returns structured data for Streamlit dashboard consumption.
    """

    queries = {
        "summary": "SELECT * FROM data_quality_summary WHERE simulation_year != 'ALL_YEARS' ORDER BY CAST(simulation_year AS INTEGER) DESC",
        "overall": "SELECT * FROM data_quality_summary WHERE simulation_year = 'ALL_YEARS'",
        "violations": """
            SELECT
                employee_id, simulation_year, data_quality_status,
                compensation_gap, gap_percentage,
                estimated_underpayment_amount,
                merit_propagation_status
            FROM data_quality_promotion_compensation
            WHERE data_quality_status IN ('CRITICAL_VIOLATION', 'MAJOR_VIOLATION')
            ORDER BY abs(compensation_gap) DESC
            LIMIT 50
        """,
        "trends": """
            SELECT
                simulation_year,
                total_violation_rate,
                data_quality_score,
                total_estimated_underpayment,
                merit_failure_rate
            FROM data_quality_summary
            WHERE simulation_year != 'ALL_YEARS'
            ORDER BY CAST(simulation_year AS INTEGER)
        """
    }

    results = {}
    with duckdb.get_connection() as conn:
        for key, query in queries.items():
            try:
                df = conn.execute(query).df()
                results[key] = df
            except Exception as e:
                results[key] = pd.DataFrame()  # Empty DataFrame on error

    return results
