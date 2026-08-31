"""Analytics service for DC Plan contribution analysis."""

import logging
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from ..models.analytics import (
    ContributionYearSummary,
    DCPlanAnalytics,
    DeferralDistributionYear,
    DeferralRateBucket,
    EscalationMetrics,
    GrandfatheredCostComparisonResponse,
    GrandfatheredCostSeries,
    GrandfatheredCostYear,
    IRSLimitMetrics,
    ParticipationByMethod,
)
from ..models.employer_cost import ForfeiturePolicy
from ..models.vesting import VestingScheduleConfig
from planalign_core.constants import TABLE_FCT_WORKFORCE_SNAPSHOT

from ..storage.workspace_storage import WorkspaceStorage
from .employer_cost_service import (
    GROSS_CORE_SQL,
    GROSS_EMPLOYER_COST_SQL,
    GROSS_MATCH_SQL,
    TOTAL_COMPENSATION_SQL,
    build_employer_cost_offsets,
    query_gross_employer_cost,
)
from .vesting_service import project_forfeitures_for_connection
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)

Cohort = Literal["all", "new_hires", "baseline"]


class AnalyticsService:
    """Service for DC Plan contribution analytics."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    @staticmethod
    def _contribution_rates(
        total_employee: float,
        total_match: float,
        total_core: float,
        total_compensation: float,
    ) -> dict:
        """Compute contribution rate percentages with division-by-zero safety."""
        if total_compensation > 0:
            emp = round(total_employee / total_compensation * 100, 2)
            match = round(total_match / total_compensation * 100, 2)
            core = round(total_core / total_compensation * 100, 2)
        else:
            emp = match = core = 0.0
        return {
            "employee_contribution_rate": emp,
            "match_contribution_rate": match,
            "core_contribution_rate": core,
            "total_contribution_rate": round(emp + match + core, 2),
        }

    @staticmethod
    def _compute_grand_totals(
        contribution_by_year: List[ContributionYearSummary],
    ) -> dict:
        """Compute aggregate totals across all contribution years."""
        total_employee = sum(
            c.total_employee_contributions for c in contribution_by_year
        )
        total_match = sum(c.total_employer_match for c in contribution_by_year)
        total_core = sum(c.total_employer_core for c in contribution_by_year)
        total_all = sum(c.total_all_contributions for c in contribution_by_year)
        total_employer_cost = total_match + total_core

        total_participants = sum(c.participant_count for c in contribution_by_year)
        avg_deferral_rate = (
            sum(
                c.average_deferral_rate * c.participant_count
                for c in contribution_by_year
            )
            / total_participants
            if total_participants > 0
            else 0.0
        )

        total_compensation = sum(c.total_compensation for c in contribution_by_year)
        employer_cost_rate = (
            (total_employer_cost / total_compensation * 100)
            if total_compensation > 0
            else 0.0
        )

        # E066: Aggregate contribution rate percentages
        rates = AnalyticsService._contribution_rates(
            total_employee,
            total_match,
            total_core,
            total_compensation,
        )

        return {
            "total_employee": total_employee,
            "total_match": total_match,
            "total_core": total_core,
            "total_all": total_all,
            "total_employer_cost": total_employer_cost,
            "avg_deferral_rate": avg_deferral_rate,
            "total_compensation": total_compensation,
            "employer_cost_rate": employer_cost_rate,
            **rates,
        }

    @staticmethod
    def _cohort_predicate(cohort: Cohort, cutoff_year: Optional[int]) -> str:
        """Return a WHERE-fragment (no leading AND/WHERE) classifying rows by cohort.

        `all` has no predicate; `new_hires` is hired on/after the supplied
        cutoff year; `baseline` is everyone else. Existing callers supply the
        resolved first simulation year, preserving Feature 134 behavior.
        """
        if cohort != "all" and cutoff_year is None:
            raise ValueError("cutoff_year is required for a cohort predicate")
        if cohort == "new_hires":
            return f"employee_hire_date >= DATE '{cutoff_year}-01-01'"
        if cohort == "baseline":
            return f"employee_hire_date < DATE '{cutoff_year}-01-01'"
        return ""

    @staticmethod
    def _combine_where(*fragments: str) -> str:
        """Join non-empty WHERE fragments with AND, prefixing WHERE/AND correctly."""
        clauses = [f for f in fragments if f]
        if not clauses:
            return ""
        return "WHERE " + " AND ".join(clauses)

    def _resolve_first_simulation_year(
        self, conn, workspace_id: str, scenario_id: str
    ) -> int:
        """Resolve the first simulation year used to classify new_hires/baseline.

        Source of truth is MIN(simulation_year) from the scenario's own
        fct_workforce_snapshot. Cross-checked (warning-only, never overriding
        the classification value) against run_metadata.start_year when that
        table exists (Feature 109; pre-Feature-109 databases lack it).
        """
        first_year = conn.execute(
            f"SELECT MIN(simulation_year) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}"
        ).fetchone()[0]
        first_year = int(first_year)

        try:
            row = conn.execute(
                "SELECT start_year FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1"
            ).fetchone()
        except Exception:
            # Pre-Feature-109 database: run_metadata table doesn't exist yet.
            row = None

        if row is not None:
            recorded_start_year = int(row[0])
            if recorded_start_year != first_year:
                logger.warning(
                    "Cohort classification year mismatch for workspace=%s "
                    "scenario=%s: fct_workforce_snapshot MIN(simulation_year)=%s "
                    "vs run_metadata.start_year=%s; using the snapshot value.",
                    workspace_id,
                    scenario_id,
                    first_year,
                    recorded_start_year,
                )

        return first_year

    @staticmethod
    def _population_by_year(conn, where_clause: str) -> Dict[int, tuple[int, Decimal]]:
        """Return cohort headcount and compensation at the yearly snapshot grain."""
        rows = conn.execute(
            f"""
            SELECT
                simulation_year,
                COUNT(*) AS headcount,
                {TOTAL_COMPENSATION_SQL} AS total_compensation
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            {where_clause}
            GROUP BY simulation_year
            ORDER BY simulation_year
            """
        ).fetchall()
        return {
            int(year): (
                int(headcount),
                Decimal(str(compensation or 0)).quantize(Decimal("0.01")),
            )
            for year, headcount, compensation in rows
        }

    @staticmethod
    def _gross_cost_by_year(conn, where_clause: str) -> Dict[int, float]:
        return {
            row.simulation_year: float(row.gross_employer_cost)
            for row in query_gross_employer_cost(conn, where_clause)
        }

    @staticmethod
    def _metadata_seed(conn) -> Optional[int]:
        """Read the selected run's seed when Feature 109 metadata is available."""
        import duckdb

        try:
            row = conn.execute(
                "SELECT random_seed FROM run_metadata "
                "ORDER BY run_timestamp DESC LIMIT 1"
            ).fetchone()
        except duckdb.Error as exc:
            logger.debug("Run metadata seed is unavailable: %s", exc)
            return None
        return int(row[0]) if row and row[0] is not None else None

    def get_grandfathered_cost_comparison(
        self,
        workspace_id: str,
        baseline_scenario_id: str,
        scenario_names: Dict[str, str],
        cutoff_year: int,
        schedule: Optional[VestingScheduleConfig] = None,
        forfeiture_policy: ForfeiturePolicy = (
            ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS
        ),
    ) -> GrandfatheredCostComparisonResponse:
        """Splice baseline pre-cutoff cost with each scenario's post-cutoff cost."""
        import duckdb

        baseline_resolved = self.db_resolver.resolve(workspace_id, baseline_scenario_id)
        if not baseline_resolved.exists:
            raise FileNotFoundError(baseline_resolved.path)

        baseline_where = self._combine_where(
            self._cohort_predicate("baseline", cutoff_year)
        )
        new_hire_where = self._combine_where(
            self._cohort_predicate("new_hires", cutoff_year)
        )
        warnings: List[str] = []
        series: List[GrandfatheredCostSeries] = []

        with duckdb.connect(
            str(baseline_resolved.path), read_only=True
        ) as baseline_conn:
            baseline_cost = self._gross_cost_by_year(baseline_conn, baseline_where)
            baseline_forfeitures = (
                project_forfeitures_for_connection(
                    baseline_conn, schedule, baseline_where
                )
                if schedule is not None
                else []
            )
            baseline_population = self._population_by_year(
                baseline_conn, baseline_where
            )
            baseline_seed = self._metadata_seed(baseline_conn)

            for scenario_id, scenario_name in scenario_names.items():
                resolved = self.db_resolver.resolve(workspace_id, scenario_id)
                if not resolved.exists:
                    raise FileNotFoundError(resolved.path)
                with duckdb.connect(str(resolved.path), read_only=True) as conn:
                    proposed_cost = self._gross_cost_by_year(conn, new_hire_where)
                    proposed_forfeitures = (
                        project_forfeitures_for_connection(
                            conn, schedule, new_hire_where
                        )
                        if schedule is not None
                        else []
                    )
                    proposed_baseline_population = self._population_by_year(
                        conn, baseline_where
                    )
                    proposed_seed = self._metadata_seed(conn)
                    if (
                        baseline_seed is not None
                        and proposed_seed is not None
                        and baseline_seed != proposed_seed
                    ):
                        warnings.append(
                            f"{scenario_name} uses random seed {proposed_seed}; "
                            f"the baseline uses {baseline_seed}."
                        )

                years = sorted(
                    set(baseline_cost)
                    | set(proposed_cost)
                    | set(baseline_population)
                    | set(proposed_baseline_population)
                )
                year_rows: List[GrandfatheredCostYear] = []
                for year in years:
                    expected = baseline_population.get(year, (0, Decimal("0.00")))
                    actual = proposed_baseline_population.get(
                        year, (0, Decimal("0.00"))
                    )
                    if expected != actual:
                        reason = (
                            "Grandfathered population differs from the baseline "
                            f"(headcount {expected[0]} vs {actual[0]}; total "
                            f"compensation ${expected[1]:,.2f} vs ${actual[1]:,.2f})."
                        )
                        year_rows.append(
                            GrandfatheredCostYear(
                                year=year, available=False, unavailable_reason=reason
                            )
                        )
                        continue

                    old_cost = baseline_cost.get(year, 0.0)
                    new_cost = proposed_cost.get(year, 0.0)
                    year_rows.append(
                        GrandfatheredCostYear(
                            year=year,
                            total_employer_cost=old_cost + new_cost,
                            baseline_cohort_cost=old_cost,
                            new_hire_cohort_cost=new_cost,
                            available=True,
                        )
                    )

                series.append(
                    GrandfatheredCostSeries(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        years=year_rows,
                        employer_cost_offsets=build_employer_cost_offsets(
                            [
                                baseline_row.model_copy(
                                    update={
                                        "terminated_employee_count": (
                                            baseline_row.terminated_employee_count
                                            + proposed_row.terminated_employee_count
                                        ),
                                        "vesting_eligible_count": (
                                            baseline_row.vesting_eligible_count
                                            + proposed_row.vesting_eligible_count
                                        ),
                                        "total_employer_contributions": (
                                            baseline_row.total_employer_contributions
                                            + proposed_row.total_employer_contributions
                                        ),
                                        "vested_amount": (
                                            baseline_row.vested_amount
                                            + proposed_row.vested_amount
                                        ),
                                        "forfeited_amount": (
                                            baseline_row.forfeited_amount
                                            + proposed_row.forfeited_amount
                                        ),
                                        "has_prior_year_basis": (
                                            baseline_row.has_prior_year_basis
                                            and proposed_row.has_prior_year_basis
                                        ),
                                    }
                                )
                                for baseline_row, proposed_row in zip(
                                    baseline_forfeitures,
                                    proposed_forfeitures,
                                    strict=True,
                                )
                            ],
                            forfeiture_policy,
                        ),
                    )
                )

        return GrandfatheredCostComparisonResponse(
            baseline_scenario_id=baseline_scenario_id,
            cutoff_year=cutoff_year,
            forfeiture_policy=forfeiture_policy,
            scenarios=series,
            warnings=warnings,
        )

    def get_dc_plan_analytics(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        active_only: bool = False,
        effective_rate: bool = False,
        cohort: Cohort = "all",
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

            first_simulation_year = self._resolve_first_simulation_year(
                conn, workspace_id, scenario_id
            )
            participation = self._get_participation_summary(
                conn, active_only, cohort, first_simulation_year
            )
            contribution_by_year = self._get_contribution_by_year(
                conn, active_only, cohort, first_simulation_year
            )
            totals = self._compute_grand_totals(contribution_by_year)
            deferral_distribution = self._get_deferral_distribution(
                conn, effective_rate=effective_rate, active_only=active_only
            )
            deferral_distribution_by_year = self._get_deferral_distribution_all_years(
                conn, effective_rate=effective_rate, active_only=active_only
            )
            escalation = self._get_escalation_metrics(conn)
            irs_limits = self._get_irs_limit_metrics(conn)

            conn.close()

            return DCPlanAnalytics(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                resolved_first_simulation_year=first_simulation_year,
                total_eligible=participation["total_eligible"],
                total_enrolled=participation["total_enrolled"],
                participation_rate=participation["participation_rate"],
                participation_by_method=participation["by_method"],
                contribution_by_year=contribution_by_year,
                total_employee_contributions=totals["total_employee"],
                total_employer_match=totals["total_match"],
                total_employer_core=totals["total_core"],
                total_all_contributions=totals["total_all"],
                deferral_rate_distribution=deferral_distribution,
                deferral_distribution_by_year=deferral_distribution_by_year,
                escalation_metrics=escalation,
                irs_limit_metrics=irs_limits,
                average_deferral_rate=round(totals["avg_deferral_rate"], 4),
                total_employer_cost=totals["total_employer_cost"],
                total_compensation=totals["total_compensation"],
                employer_cost_rate=round(totals["employer_cost_rate"], 2),
                # E066: Contribution rate percentages
                employee_contribution_rate=round(
                    totals["employee_contribution_rate"], 2
                ),
                match_contribution_rate=round(totals["match_contribution_rate"], 2),
                core_contribution_rate=round(totals["core_contribution_rate"], 2),
                total_contribution_rate=round(totals["total_contribution_rate"], 2),
            )

        except Exception as e:
            logger.error(f"Failed to get DC plan analytics: {e}")
            return None

    def _get_participation_summary(
        self,
        conn,
        active_only: bool = False,
        cohort: Cohort = "all",
        first_simulation_year: Optional[int] = None,
    ) -> dict:
        """Get participation summary from final simulation year.

        Args:
            active_only: If True, filter to active employees only.
                         If False (default), include all employees (active + terminated).
            cohort: Population filter — `all`, `new_hires`, or `baseline` (FR-004).
            first_simulation_year: Required when cohort != "all"; the year that
                classifies new_hires vs baseline (see _resolve_first_simulation_year).
        """
        try:
            status_filter = "UPPER(employment_status) = 'ACTIVE'" if active_only else ""
            cohort_filter = self._cohort_predicate(cohort, first_simulation_year)
            where_clause = self._combine_where(
                "simulation_year = final_year.max_year", status_filter, cohort_filter
            )
            result = conn.execute(
                f"""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                )
                SELECT
                    COUNT(*) as total_eligible,
                    SUM(CASE WHEN is_enrolled_flag THEN 1 ELSE 0 END) as total_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%auto%' THEN 1 ELSE 0 END) as auto_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%voluntary%' THEN 1 ELSE 0 END) as voluntary_enrolled,
                    SUM(CASE WHEN participation_status_detail ILIKE '%census%'
                              OR participation_status_detail ILIKE '%baseline%' THEN 1 ELSE 0 END) as census_enrolled
                FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}, final_year
                {where_clause}
            """
            ).fetchone()

            total_eligible = result[0] or 0
            total_enrolled = result[1] or 0
            auto_enrolled = result[2] or 0
            voluntary_enrolled = result[3] or 0
            census_enrolled = result[4] or 0

            participation_rate = (
                (total_enrolled / total_eligible * 100) if total_eligible > 0 else 0.0
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
        self,
        conn,
        active_only: bool = False,
        cohort: Cohort = "all",
        first_simulation_year: Optional[int] = None,
    ) -> List[ContributionYearSummary]:
        """Get contribution totals by simulation year.

        Args:
            active_only: If True, filter to active employees only.
                         If False (default), include all employees (active + terminated).
            cohort: Population filter — `all`, `new_hires`, or `baseline` (FR-004).
            first_simulation_year: Required when cohort != "all"; the year that
                classifies new_hires vs baseline (see _resolve_first_simulation_year).
        """
        try:
            # E104: Enhanced query with average deferral rate, participation rate, and total employer cost
            # E013: Added total_compensation for employer cost rate calculation
            status_filter = "UPPER(employment_status) = 'ACTIVE'" if active_only else ""
            cohort_filter = self._cohort_predicate(cohort, first_simulation_year)
            where_clause = self._combine_where(status_filter, cohort_filter)
            participation_rate_expr = (
                "COALESCE(COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 "
                "/ NULLIF(COUNT(*), 0), 0)"
            )

            df = conn.execute(
                f"""
                SELECT
                    simulation_year as year,
                    COALESCE(SUM(prorated_annual_contributions), 0) as total_employee,
                    {GROSS_MATCH_SQL} as total_match,
                    {GROSS_CORE_SQL} as total_core,
                    {GROSS_EMPLOYER_COST_SQL} as total_employer_cost,
                    COALESCE(SUM(prorated_annual_contributions) + SUM(employer_match_amount) + SUM(employer_core_amount), 0) as total_all,
                    AVG(CASE WHEN is_enrolled_flag THEN current_deferral_rate ELSE NULL END) as avg_deferral_rate,
                    {participation_rate_expr} as participation_rate,
                    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) as participant_count,
                    COUNT(*) as total_eligible,
                    {TOTAL_COMPENSATION_SQL} as total_compensation
                FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                {where_clause}
                GROUP BY simulation_year
                ORDER BY simulation_year
            """
            ).fetchdf()

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
                # E066: Calculate contribution rate percentages
                total_employee = float(row["total_employee"])
                total_match = float(row["total_match"])
                total_core = float(row["total_core"])
                rates = self._contribution_rates(
                    total_employee,
                    total_match,
                    total_core,
                    total_compensation,
                )
                results.append(
                    ContributionYearSummary(
                        year=int(row["year"]),
                        total_employee_contributions=total_employee,
                        total_employer_match=total_match,
                        total_employer_core=total_core,
                        total_all_contributions=float(row["total_all"]),
                        participant_count=int(row["participant_count"]),
                        total_eligible_count=int(row["total_eligible"]),
                        # E104: New fields
                        average_deferral_rate=float(row["avg_deferral_rate"] or 0.0),
                        participation_rate=round(
                            float(row["participation_rate"] or 0.0), 2
                        ),
                        total_employer_cost=total_employer_cost,
                        # E013: Employer cost ratio metrics
                        total_compensation=total_compensation,
                        employer_cost_rate=round(employer_cost_rate, 2),
                        # E066: Contribution rate percentages
                        employee_contribution_rate=rates["employee_contribution_rate"],
                        match_contribution_rate=rates["match_contribution_rate"],
                        core_contribution_rate=rates["core_contribution_rate"],
                        total_contribution_rate=rates["total_contribution_rate"],
                    )
                )
            return results
        except Exception as e:
            logger.warning(f"Failed to get contribution by year: {e}")
            return []

    def _get_deferral_distribution(
        self,
        conn,
        effective_rate: bool = False,
        active_only: bool = False,
    ) -> List[DeferralRateBucket]:
        """Get deferral rate distribution (11 buckets: 0%, 1%...9%, 10%+).

        effective_rate=True  → uses effective_annual_deferral_rate (matches contribution
                               calculation) with the same population as participation rate.
        effective_rate=False → uses current_deferral_rate (year-end snapshot, active only).
        """
        rate_col = (
            "effective_annual_deferral_rate"
            if effective_rate
            else "current_deferral_rate"
        )
        if effective_rate:
            status_filter = (
                "AND UPPER(employment_status) = 'ACTIVE'" if active_only else ""
            )
        else:
            status_filter = "AND UPPER(employment_status) = 'ACTIVE'"
        try:
            # Query for distribution buckets
            df = conn.execute(
                f"""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                ),
                bucketed AS (
                    SELECT
                        CASE
                            WHEN {rate_col} IS NULL OR {rate_col} = 0 THEN '0%'
                            WHEN {rate_col} < 0.015 THEN '1%'
                            WHEN {rate_col} < 0.025 THEN '2%'
                            WHEN {rate_col} < 0.035 THEN '3%'
                            WHEN {rate_col} < 0.045 THEN '4%'
                            WHEN {rate_col} < 0.055 THEN '5%'
                            WHEN {rate_col} < 0.065 THEN '6%'
                            WHEN {rate_col} < 0.075 THEN '7%'
                            WHEN {rate_col} < 0.085 THEN '8%'
                            WHEN {rate_col} < 0.095 THEN '9%'
                            ELSE '10%+'
                        END as bucket
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}, final_year
                    WHERE simulation_year = final_year.max_year
                      {status_filter}
                )
                SELECT
                    bucket,
                    COUNT(*) as count
                FROM bucketed
                GROUP BY bucket
            """
            ).fetchdf()

            # Create a complete list with all buckets
            bucket_order = [
                "0%",
                "1%",
                "2%",
                "3%",
                "4%",
                "5%",
                "6%",
                "7%",
                "8%",
                "9%",
                "10%+",
            ]
            bucket_counts = {
                row["bucket"]: int(row["count"]) for _, row in df.iterrows()
            }

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
                for b in [
                    "0%",
                    "1%",
                    "2%",
                    "3%",
                    "4%",
                    "5%",
                    "6%",
                    "7%",
                    "8%",
                    "9%",
                    "10%+",
                ]
            ]

    def _get_deferral_distribution_all_years(
        self,
        conn,
        effective_rate: bool = False,
        active_only: bool = False,
    ) -> List[DeferralDistributionYear]:
        """Get deferral rate distribution for all simulation years (E059).

        effective_rate=True  → uses effective_annual_deferral_rate with participation-rate
                               population (respects active_only).
        effective_rate=False → uses current_deferral_rate, active employees only.
        """
        rate_col = (
            "effective_annual_deferral_rate"
            if effective_rate
            else "current_deferral_rate"
        )
        if effective_rate:
            status_filter = (
                "WHERE UPPER(employment_status) = 'ACTIVE'" if active_only else ""
            )
        else:
            status_filter = "WHERE UPPER(employment_status) = 'ACTIVE'"
        bucket_order = [
            "0%",
            "1%",
            "2%",
            "3%",
            "4%",
            "5%",
            "6%",
            "7%",
            "8%",
            "9%",
            "10%+",
        ]
        try:
            df = conn.execute(
                f"""
                WITH bucketed AS (
                    SELECT
                        simulation_year,
                        CASE
                            WHEN {rate_col} IS NULL OR {rate_col} = 0 THEN '0%'
                            WHEN {rate_col} < 0.015 THEN '1%'
                            WHEN {rate_col} < 0.025 THEN '2%'
                            WHEN {rate_col} < 0.035 THEN '3%'
                            WHEN {rate_col} < 0.045 THEN '4%'
                            WHEN {rate_col} < 0.055 THEN '5%'
                            WHEN {rate_col} < 0.065 THEN '6%'
                            WHEN {rate_col} < 0.075 THEN '7%'
                            WHEN {rate_col} < 0.085 THEN '8%'
                            WHEN {rate_col} < 0.095 THEN '9%'
                            ELSE '10%+'
                        END as bucket
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                    {status_filter}
                )
                SELECT
                    simulation_year,
                    bucket,
                    COUNT(*) as count
                FROM bucketed
                GROUP BY simulation_year, bucket
                ORDER BY simulation_year, bucket
            """
            ).fetchdf()

            # Group by year
            years_data: dict = {}
            for _, row in df.iterrows():
                year = int(row["simulation_year"])
                bucket = str(row["bucket"])
                count = int(row["count"])
                if year not in years_data:
                    years_data[year] = {}
                years_data[year][bucket] = count

            results = []
            for year in sorted(years_data.keys()):
                bucket_counts = years_data[year]
                total_count = sum(bucket_counts.values())

                distribution = [
                    DeferralRateBucket(
                        bucket=b,
                        count=bucket_counts.get(b, 0),
                        percentage=(
                            round(bucket_counts.get(b, 0) / total_count * 100, 2)
                            if total_count > 0
                            else 0.0
                        ),
                    )
                    for b in bucket_order
                ]
                results.append(
                    DeferralDistributionYear(year=year, distribution=distribution)
                )

            return results
        except Exception as e:
            logger.warning(f"Failed to get deferral distribution by year: {e}")
            return []

    def _get_escalation_metrics(self, conn) -> EscalationMetrics:
        """Get deferral escalation metrics."""
        try:
            result = conn.execute(
                f"""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                )
                SELECT
                    SUM(CASE WHEN has_deferral_escalations THEN 1 ELSE 0 END) as employees_with_escalations,
                    AVG(CASE WHEN has_deferral_escalations THEN total_deferral_escalations ELSE NULL END) as avg_escalations,
                    SUM(COALESCE(total_escalation_amount, 0)) as total_escalation_amount
                FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}, final_year
                WHERE simulation_year = final_year.max_year
                  AND UPPER(employment_status) = 'ACTIVE'
                  AND is_enrolled_flag = true
            """
            ).fetchone()

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
            result = conn.execute(
                f"""
                WITH final_year AS (
                    SELECT MAX(simulation_year) as max_year
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
                ),
                participants AS (
                    SELECT
                        COUNT(*) as total_participants,
                        SUM(CASE WHEN irs_limit_reached THEN 1 ELSE 0 END) as at_limit
                    FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}, final_year
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
            """
            ).fetchone()

            return IRSLimitMetrics(
                employees_at_irs_limit=int(result[0] or 0),
                irs_limit_rate=round(float(result[1] or 0), 2),
            )
        except Exception as e:
            logger.warning(f"Failed to get IRS limit metrics: {e}")
            return IRSLimitMetrics(employees_at_irs_limit=0, irs_limit_rate=0.0)
