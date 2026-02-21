"""Analytics service for DC Plan contribution analysis."""

import logging
from pathlib import Path
from typing import List, Optional

from ..models.analytics import (
    ContributionYearSummary,
    DCPlanAnalytics,
    DeferralRateBucket,
    EscalationMetrics,
    IRSLimitMetrics,
    ParticipationByMethod,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for DC Plan contribution analytics."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def get_dc_plan_analytics(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        active_only: bool = False,
    ) -> Optional[DCPlanAnalytics]:
        """
        Get DC Plan analytics for a single scenario.

        Queries fct_workforce_snapshot for contribution data.
        """
        try:
            import duckdb

            resolved = self.db_resolver.resolve(workspace_id, scenario_id)
            if not resolved.exists:
                logger.error(f"Database not found for scenario {scenario_id}")
                return None

            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Get participation summary (from final year)
            participation = self._get_participation_summary(conn, active_only)

            # Get contribution totals by year
            contribution_by_year = self._get_contribution_by_year(conn, active_only)

            # Calculate grand totals
            total_employee = sum(c.total_employee_contributions for c in contribution_by_year)
            total_match = sum(c.total_employer_match for c in contribution_by_year)
            total_core = sum(c.total_employer_core for c in contribution_by_year)
            total_all = sum(c.total_all_contributions for c in contribution_by_year)
            # E104: Calculate total employer cost and weighted average deferral rate
            total_employer_cost = total_match + total_core
            # Weighted average deferral rate across all years (weighted by participant count)
            total_participants = sum(c.participant_count for c in contribution_by_year)
            avg_deferral_rate = (
                sum(c.average_deferral_rate * c.participant_count for c in contribution_by_year)
                / total_participants
                if total_participants > 0
                else 0.0
            )
            # E013: Calculate aggregate total_compensation and employer_cost_rate
            total_compensation = sum(c.total_compensation for c in contribution_by_year)
            employer_cost_rate = (
                (total_employer_cost / total_compensation * 100)
                if total_compensation > 0
                else 0.0
            )

            # Get deferral rate distribution
            deferral_distribution = self._get_deferral_distribution(conn)

            # Get escalation metrics
            escalation = self._get_escalation_metrics(conn)

            # Get IRS limit metrics
            irs_limits = self._get_irs_limit_metrics(conn)

            conn.close()

            return DCPlanAnalytics(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                total_eligible=participation["total_eligible"],
                total_enrolled=participation["total_enrolled"],
                participation_rate=participation["participation_rate"],
                participation_by_method=participation["by_method"],
                contribution_by_year=contribution_by_year,
                total_employee_contributions=total_employee,
                total_employer_match=total_match,
                total_employer_core=total_core,
                total_all_contributions=total_all,
                deferral_rate_distribution=deferral_distribution,
                escalation_metrics=escalation,
                irs_limit_metrics=irs_limits,
                # E104: New fields for cost comparison
                average_deferral_rate=round(avg_deferral_rate, 4),
                total_employer_cost=total_employer_cost,
                # E013: Employer cost ratio metrics
                total_compensation=total_compensation,
                employer_cost_rate=round(employer_cost_rate, 2),
            )

        except Exception as e:
            logger.error(f"Failed to get DC plan analytics: {e}")
            return None

    def _get_participation_summary(self, conn, active_only: bool = False) -> dict:
        """Get participation summary from final simulation year.

        Args:
            active_only: If True, filter to active employees only.
                         If False (default), include all employees (active + terminated).
        """
        try:
            status_filter = (
                "AND UPPER(employment_status) = 'ACTIVE'"
                if active_only
                else ""
            )
            result = conn.execute(f"""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM fct_workforce_snapshot
                )
                SELECT
                    COUNT(*) as total_eligible,
                    SUM(CASE WHEN is_enrolled_flag THEN 1 ELSE 0 END) as total_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%auto%' THEN 1 ELSE 0 END) as auto_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%voluntary%' THEN 1 ELSE 0 END) as voluntary_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%census%'
                              OR participation_status_detail ILIKE '%baseline%' THEN 1 ELSE 0 END) as census_enrolled
                FROM fct_workforce_snapshot, final_year
                WHERE simulation_year = final_year.max_year
                  {status_filter}
            """).fetchone()

            total_eligible = result[0] or 0
            total_enrolled = result[1] or 0
            auto_enrolled = result[2] or 0
            voluntary_enrolled = result[3] or 0
            census_enrolled = result[4] or 0

            participation_rate = (
                (total_enrolled / total_eligible * 100)
                if total_eligible > 0
                else 0.0
            )

            return {
                "total_eligible": total_eligible,
                "total_enrolled": total_enrolled,
                "participation_rate": round(participation_rate, 2),
                "by_method": ParticipationByMethod(
                    auto_enrolled=auto_enrolled,
                    voluntary_enrolled=voluntary_enrolled,
                    census_enrolled=census_enrolled,
                ),
            }
        except Exception as e:
            logger.warning(f"Failed to get participation summary: {e}")
            return {
                "total_eligible": 0,
                "total_enrolled": 0,
                "participation_rate": 0.0,
                "by_method": ParticipationByMethod(
                    auto_enrolled=0, voluntary_enrolled=0, census_enrolled=0
                ),
            }

    def _get_contribution_by_year(
        self, conn, active_only: bool = False
    ) -> List[ContributionYearSummary]:
        """Get contribution totals by simulation year.

        Args:
            active_only: If True, filter to active employees only.
                         If False (default), include all employees (active + terminated).
        """
        try:
            # E104: Enhanced query with average deferral rate, participation rate, and total employer cost
            # E013: Added total_compensation for employer cost rate calculation
            if active_only:
                status_filter = "WHERE UPPER(employment_status) = 'ACTIVE'"
                participation_rate_expr = (
                    "COALESCE(COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 "
                    "/ NULLIF(COUNT(*), 0), 0)"
                )
            else:
                status_filter = ""
                participation_rate_expr = (
                    "COALESCE(COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 "
                    "/ NULLIF(COUNT(*), 0), 0)"
                )

            df = conn.execute(f"""
                SELECT
                    simulation_year as year,
                    COALESCE(SUM(prorated_annual_contributions), 0) as total_employee,
                    COALESCE(SUM(employer_match_amount), 0) as total_match,
                    COALESCE(SUM(employer_core_amount), 0) as total_core,
                    COALESCE(SUM(employer_match_amount) + SUM(employer_core_amount), 0) as total_employer_cost,
                    COALESCE(SUM(prorated_annual_contributions) + SUM(employer_match_amount) + SUM(employer_core_amount), 0) as total_all,
                    AVG(CASE WHEN is_enrolled_flag THEN current_deferral_rate ELSE NULL END) as avg_deferral_rate,
                    {participation_rate_expr} as participation_rate,
                    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) as participant_count,
                    COALESCE(SUM(prorated_annual_compensation), 0) as total_compensation
                FROM fct_workforce_snapshot
                {status_filter}
                GROUP BY simulation_year
                ORDER BY simulation_year
            """).fetchdf()

            results = []
            for _, row in df.iterrows():
                total_employer_cost = float(row["total_employer_cost"])
                total_compensation = float(row["total_compensation"])
                # E013: Calculate employer cost rate (as percentage)
                employer_cost_rate = (
                    (total_employer_cost / total_compensation * 100)
                    if total_compensation > 0
                    else 0.0
                )
                results.append(
                    ContributionYearSummary(
                        year=int(row["year"]),
                        total_employee_contributions=float(row["total_employee"]),
                        total_employer_match=float(row["total_match"]),
                        total_employer_core=float(row["total_core"]),
                        total_all_contributions=float(row["total_all"]),
                        participant_count=int(row["participant_count"]),
                        # E104: New fields
                        average_deferral_rate=float(row["avg_deferral_rate"] or 0.0),
                        participation_rate=round(float(row["participation_rate"] or 0.0), 2),
                        total_employer_cost=total_employer_cost,
                        # E013: Employer cost ratio metrics
                        total_compensation=total_compensation,
                        employer_cost_rate=round(employer_cost_rate, 2),
                    )
                )
            return results
        except Exception as e:
            logger.warning(f"Failed to get contribution by year: {e}")
            return []

    def _get_deferral_distribution(self, conn) -> List[DeferralRateBucket]:
        """Get deferral rate distribution (11 buckets: 0%, 1%...9%, 10%+)."""
        try:
            # Query for distribution buckets
            df = conn.execute("""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM fct_workforce_snapshot
                ),
                bucketed AS (
                    SELECT
                        CASE
                            WHEN current_deferral_rate IS NULL OR current_deferral_rate = 0 THEN '0%'
                            WHEN current_deferral_rate < 0.015 THEN '1%'
                            WHEN current_deferral_rate < 0.025 THEN '2%'
                            WHEN current_deferral_rate < 0.035 THEN '3%'
                            WHEN current_deferral_rate < 0.045 THEN '4%'
                            WHEN current_deferral_rate < 0.055 THEN '5%'
                            WHEN current_deferral_rate < 0.065 THEN '6%'
                            WHEN current_deferral_rate < 0.075 THEN '7%'
                            WHEN current_deferral_rate < 0.085 THEN '8%'
                            WHEN current_deferral_rate < 0.095 THEN '9%'
                            ELSE '10%+'
                        END as bucket
                    FROM fct_workforce_snapshot, final_year
                    WHERE simulation_year = final_year.max_year
                      AND UPPER(employment_status) = 'ACTIVE'
                      AND is_enrolled_flag = true
                )
                SELECT
                    bucket,
                    COUNT(*) as count
                FROM bucketed
                GROUP BY bucket
            """).fetchdf()

            # Create a complete list with all buckets
            bucket_order = ['0%', '1%', '2%', '3%', '4%', '5%', '6%', '7%', '8%', '9%', '10%+']
            bucket_counts = {row["bucket"]: int(row["count"]) for _, row in df.iterrows()}

            total_count = sum(bucket_counts.values())

            return [
                DeferralRateBucket(
                    bucket=bucket,
                    count=bucket_counts.get(bucket, 0),
                    percentage=(
                        round(bucket_counts.get(bucket, 0) / total_count * 100, 2)
                        if total_count > 0
                        else 0.0
                    ),
                )
                for bucket in bucket_order
            ]
        except Exception as e:
            logger.warning(f"Failed to get deferral distribution: {e}")
            return [
                DeferralRateBucket(bucket=b, count=0, percentage=0.0)
                for b in ['0%', '1%', '2%', '3%', '4%', '5%', '6%', '7%', '8%', '9%', '10%+']
            ]

    def _get_escalation_metrics(self, conn) -> EscalationMetrics:
        """Get deferral escalation metrics."""
        try:
            result = conn.execute("""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM fct_workforce_snapshot
                )
                SELECT
                    SUM(CASE WHEN has_deferral_escalations THEN 1 ELSE 0 END) as employees_with_escalations,
                    AVG(CASE WHEN has_deferral_escalations THEN total_deferral_escalations ELSE NULL END) as avg_escalations,
                    SUM(COALESCE(total_escalation_amount, 0)) as total_escalation_amount
                FROM fct_workforce_snapshot, final_year
                WHERE simulation_year = final_year.max_year
                  AND UPPER(employment_status) = 'ACTIVE'
                  AND is_enrolled_flag = true
            """).fetchone()

            return EscalationMetrics(
                employees_with_escalations=int(result[0] or 0),
                avg_escalation_count=round(float(result[1] or 0), 2),
                total_escalation_amount=round(float(result[2] or 0), 4),
            )
        except Exception as e:
            logger.warning(f"Failed to get escalation metrics: {e}")
            return EscalationMetrics(
                employees_with_escalations=0,
                avg_escalation_count=0.0,
                total_escalation_amount=0.0,
            )

    def _get_irs_limit_metrics(self, conn) -> IRSLimitMetrics:
        """Get IRS contribution limit metrics."""
        try:
            result = conn.execute("""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM fct_workforce_snapshot
                ),
                participants AS (
                    SELECT
                        COUNT(*) as total_participants,
                        SUM(CASE WHEN irs_limit_reached THEN 1 ELSE 0 END) as at_limit
                    FROM fct_workforce_snapshot, final_year
                    WHERE simulation_year = final_year.max_year
                      AND UPPER(employment_status) = 'ACTIVE'
                      AND is_enrolled_flag = true
                )
                SELECT
                    at_limit,
                    CASE
                        WHEN total_participants > 0
                        THEN at_limit * 100.0 / total_participants
                        ELSE 0
                    END as limit_rate
                FROM participants
            """).fetchone()

            return IRSLimitMetrics(
                employees_at_irs_limit=int(result[0] or 0),
                irs_limit_rate=round(float(result[1] or 0), 2),
            )
        except Exception as e:
            logger.warning(f"Failed to get IRS limit metrics: {e}")
            return IRSLimitMetrics(employees_at_irs_limit=0, irs_limit_rate=0.0)
