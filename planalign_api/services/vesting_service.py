"""Vesting analysis service for schedule comparison and forfeiture projections."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from ..models.vesting import (
    EmployeeVestingDetail,
    ForfeitureProjectionResponse,
    ForfeitureYearRow,
    ScenarioForfeitureSeries,
    ScenarioYearsResponse,
    SkippedScenario,
    TenureBandSummary,
    VestingAnalysisRequest,
    VestingAnalysisResponse,
    VestingAnalysisSummary,
    VestingScheduleConfig,
    VestingScheduleInfo,
    VestingScheduleListResponse,
    VestingScheduleType,
)
from ..models.employer_cost import ForfeiturePolicy
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)
from .employer_cost_service import build_employer_cost_offsets

logger = logging.getLogger(__name__)


# Pre-defined vesting schedules (T014)
VESTING_SCHEDULES: dict[VestingScheduleType, dict[int, float]] = {
    VestingScheduleType.IMMEDIATE: {0: 1.0},
    VestingScheduleType.CLIFF_1_YEAR: {0: 0.0, 1: 1.0},
    VestingScheduleType.CLIFF_2_YEAR: {0: 0.0, 1: 0.0, 2: 1.0},
    VestingScheduleType.CLIFF_3_YEAR: {0: 0.0, 1: 0.0, 2: 0.0, 3: 1.0},
    VestingScheduleType.CLIFF_4_YEAR: {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 1.0},
    VestingScheduleType.QACA_2_YEAR: {0: 0.0, 1: 0.0, 2: 1.0},
    VestingScheduleType.GRADED_3_YEAR: {0: 0.0, 1: 0.3333, 2: 0.6667, 3: 1.0},
    VestingScheduleType.GRADED_4_YEAR: {0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0},
    VestingScheduleType.GRADED_5_YEAR: {
        0: 0.0,
        1: 0.20,
        2: 0.40,
        3: 0.60,
        4: 0.80,
        5: 1.0,
    },
    VestingScheduleType.GRADED_6_YEAR: {
        0: 0.0,
        1: 0.0,
        2: 0.20,
        3: 0.40,
        4: 0.60,
        5: 0.80,
        6: 1.0,
    },
}


# Schedule display information (T015)
SCHEDULE_INFO: dict[VestingScheduleType, VestingScheduleInfo] = {
    VestingScheduleType.IMMEDIATE: VestingScheduleInfo(
        schedule_type=VestingScheduleType.IMMEDIATE,
        name="Immediate",
        description="100% vested from day one",
        percentages={0: 1.0},
    ),
    VestingScheduleType.CLIFF_1_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_1_YEAR,
        name="1-Year Cliff",
        description="0% until 1 year, then 100%",
        percentages={0: 0.0, 1: 1.0},
    ),
    VestingScheduleType.CLIFF_2_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_2_YEAR,
        name="2-Year Cliff",
        description="0% until 2 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 1.0},
    ),
    VestingScheduleType.CLIFF_3_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_3_YEAR,
        name="3-Year Cliff",
        description="0% until 3 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 0.0, 3: 1.0},
    ),
    VestingScheduleType.CLIFF_4_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_4_YEAR,
        name="4-Year Cliff",
        description="0% until 4 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 1.0},
    ),
    VestingScheduleType.QACA_2_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.QACA_2_YEAR,
        name="QACA 2-Year",
        description="0% until 2 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 1.0},
    ),
    VestingScheduleType.GRADED_3_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_3_YEAR,
        name="3-Year Graded",
        description="33.33% per year from year 1-3",
        percentages={0: 0.0, 1: 0.3333, 2: 0.6667, 3: 1.0},
    ),
    VestingScheduleType.GRADED_4_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_4_YEAR,
        name="4-Year Graded",
        description="25% per year from year 1-4",
        percentages={0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0},
    ),
    VestingScheduleType.GRADED_5_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_5_YEAR,
        name="5-Year Graded",
        description="20% per year from year 1-5",
        percentages={0: 0.0, 1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 1.0},
    ),
    VestingScheduleType.GRADED_6_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_6_YEAR,
        name="6-Year Graded",
        description="0% through year 1, then 20% per year from year 2-6",
        percentages={
            0: 0.0,
            1: 0.0,
            2: 0.20,
            3: 0.40,
            4: 0.60,
            5: 0.80,
            6: 1.0,
        },
    ),
}


def get_vesting_percentage(
    schedule_type: VestingScheduleType,
    tenure_years: float,
    annual_hours: Optional[int] = None,
    require_hours: bool = False,
    hours_threshold: int = 1000,
) -> Decimal:
    """
    Calculate vesting percentage for a given schedule and tenure (T016).

    Args:
        schedule_type: One of the pre-defined schedule types
        tenure_years: Years of service (will be truncated to int)
        annual_hours: Hours worked in final year
        require_hours: If True, check hours threshold
        hours_threshold: Minimum hours for vesting credit

    Returns:
        Vesting percentage as Decimal (0.0 to 1.0)
    """
    schedule = VESTING_SCHEDULES.get(schedule_type)
    if not schedule:
        raise ValueError(f"Unknown schedule type: {schedule_type}")

    # Apply hours credit adjustment
    effective_tenure = int(tenure_years)
    if require_hours and annual_hours is not None:
        if annual_hours < hours_threshold:
            effective_tenure = max(0, effective_tenure - 1)

    # Clamp to max year in schedule
    max_year = max(schedule.keys())
    effective_tenure = min(effective_tenure, max_year)

    return Decimal(str(schedule.get(effective_tenure, schedule[max_year])))


def calculate_forfeiture(total_contributions: Decimal, vesting_pct: Decimal) -> Decimal:
    """Calculate forfeiture amount (T017)."""
    unvested = Decimal("1.0") - vesting_pct
    return (total_contributions * unvested).quantize(Decimal("0.01"))


def get_schedule_list() -> VestingScheduleListResponse:
    """Return list of all available vesting schedules (T018)."""
    return VestingScheduleListResponse(schedules=list(SCHEDULE_INFO.values()))


# ---------------------------------------------------------------------------
# Connection-level forfeiture projection
# ---------------------------------------------------------------------------
# These take a DuckDB connection rather than a workspace, so the CLI, the Excel
# export and the net-cost service (#444) can reach the same numbers the Vesting
# screens show without going through workspace storage.


def _terminated_employees_all_years(conn, where_clause: str = "") -> List[dict]:
    """Every contribution-qualified termination, all years, in one query.

    Same cumulative basis as :meth:`VestingService._get_terminated_employees`
    (issue #444): an employee's forfeiture basis is the sum of the employer
    contributions they accrued in every simulation year before the year they
    terminated, not the single prior year.
    """
    status_joiner = "AND" if where_clause else "WHERE"
    query = f"""
        WITH terminated AS (
            SELECT
                simulation_year,
                employee_id,
                current_tenure,
                tenure_band,
                COALESCE(annual_hours_worked, 0) AS annual_hours_worked
            FROM fct_workforce_snapshot
            {where_clause}
            {status_joiner} UPPER(employment_status) = 'TERMINATED'
        ),
        contributions AS (
            SELECT
                simulation_year,
                employee_id,
                COALESCE(total_employer_contributions, 0)
                    AS total_employer_contributions
            FROM fct_workforce_snapshot
            WHERE UPPER(employment_status) = 'ACTIVE'
        )
        SELECT
            t.simulation_year,
            t.employee_id,
            t.current_tenure,
            t.tenure_band,
            t.annual_hours_worked,
            COALESCE(SUM(c.total_employer_contributions), 0)
                AS total_employer_contributions
        FROM terminated t
        LEFT JOIN contributions c
          ON c.employee_id = t.employee_id
         AND c.simulation_year < t.simulation_year
        GROUP BY
            t.simulation_year,
            t.employee_id,
            t.current_tenure,
            t.tenure_band,
            t.annual_hours_worked
        HAVING COALESCE(SUM(c.total_employer_contributions), 0) > 0
        ORDER BY t.simulation_year, t.employee_id
    """
    columns = [
        "simulation_year",
        "employee_id",
        "current_tenure",
        "tenure_band",
        "annual_hours_worked",
        "total_employer_contributions",
    ]
    return [dict(zip(columns, row)) for row in conn.execute(query).fetchall()]


def _terminated_counts_by_year(conn, where_clause: str = "") -> dict[int, int]:
    """All terminations per year, regardless of contribution basis."""
    rows = conn.execute(
        f"""
        SELECT simulation_year, COUNT(*)
        FROM fct_workforce_snapshot
        {where_clause}
        {"AND" if where_clause else "WHERE"}
            UPPER(employment_status) = 'TERMINATED'
        GROUP BY simulation_year
        """
    ).fetchall()
    return {int(year): int(count) for year, count in rows}


def _simulation_years(conn) -> List[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT simulation_year
        FROM fct_workforce_snapshot
        ORDER BY simulation_year
        """
    ).fetchall()
    return [int(row[0]) for row in rows]


def _forfeiture_row(
    year: int,
    employees: List[dict],
    terminated_count: int,
    schedule: VestingScheduleConfig,
    has_prior_year_basis: bool,
) -> ForfeitureYearRow:
    """Apply one schedule to one year's qualified terminations."""
    contributions = Decimal("0")
    vested = Decimal("0")
    forfeited = Decimal("0")

    for emp in employees:
        amount = Decimal(str(emp["total_employer_contributions"]))
        pct = get_vesting_percentage(
            schedule.schedule_type,
            emp["current_tenure"] or 0,
            emp["annual_hours_worked"] or 0,
            schedule.require_hours_credit,
            schedule.hours_threshold,
        )
        contributions += amount
        vested += (amount * pct).quantize(Decimal("0.01"))
        forfeited += calculate_forfeiture(amount, pct)

    return ForfeitureYearRow(
        simulation_year=year,
        has_prior_year_basis=has_prior_year_basis,
        terminated_employee_count=terminated_count,
        vesting_eligible_count=len(employees),
        total_employer_contributions=contributions,
        vested_amount=vested,
        forfeited_amount=forfeited,
    )


def project_forfeitures_for_connection(
    conn, schedule: VestingScheduleConfig, where_clause: str = ""
) -> List[ForfeitureYearRow]:
    """Forfeitures under one schedule for every year in an open database.

    Returns an empty list when the database contains no simulation years. The
    scenario's first year is flagged ``has_prior_year_basis=False``: its
    terminations accrued their employer money before the horizon, so their
    forfeiture is unmeasurable rather than zero.

    ``where_clause`` filters the employees whose terminations are projected.
    Their contribution basis still includes every prior simulation year.
    """
    years = _simulation_years(conn)
    if not years:
        return []

    by_year: dict[int, List[dict]] = {year: [] for year in years}
    for emp in _terminated_employees_all_years(conn, where_clause):
        by_year.setdefault(int(emp["simulation_year"]), []).append(emp)

    terminated_counts = _terminated_counts_by_year(conn, where_clause)
    first_year = min(years)

    return [
        _forfeiture_row(
            year,
            by_year.get(year, []),
            terminated_counts.get(year, 0),
            schedule,
            has_prior_year_basis=year != first_year,
        )
        for year in years
    ]


class VestingService:
    """Service for vesting analysis comparing schedules."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        """Initialize with storage and database resolver (T023)."""
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def _get_final_year(self, conn) -> int:
        """Get the maximum simulation year from the database (T024)."""
        result = conn.execute(
            "SELECT MAX(simulation_year) FROM fct_workforce_snapshot"
        ).fetchone()
        return result[0] if result and result[0] else 2025

    def get_available_years(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[ScenarioYearsResponse]:
        """Get available simulation years for a scenario."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            logger.error(f"Database not found for scenario {scenario_id}")
            return None

        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            rows = conn.execute(
                "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year ASC"
            ).fetchall()
            years = [row[0] for row in rows]
            if not years:
                return None
            return ScenarioYearsResponse(
                years=years,
                default_year=max(years),
            )
        finally:
            conn.close()

    def _get_terminated_employees(self, conn, year: int) -> List[dict]:
        """Query terminated employees with their cumulative employer balance.

        The forfeiture basis is the employee's *cumulative* employer
        contributions across every simulation year before the termination year
        (issue #444), not the single prior year. An employee on a 3-year cliff
        who terminates in year three forfeits three years of employer money, not
        one. Termination zeroes the current year's columns in the snapshot and
        the pipeline funds no employer contribution in the termination year, so
        summing the prior active years is the whole in-horizon balance.

        Contributions made before the first simulation year are outside the run
        and are not in the basis; that limitation is stated in the methodology
        copy on every surface that reports these figures.
        """
        query = """
            WITH terminated_this_year AS (
                SELECT
                    t.employee_id,
                    t.employee_hire_date,
                    t.termination_date,
                    t.current_tenure,
                    t.tenure_band,
                    COALESCE(t.annual_hours_worked, 0) as annual_hours_worked
                FROM fct_workforce_snapshot t
                WHERE t.simulation_year = ?
                  AND UPPER(t.employment_status) = 'TERMINATED'
            ),
            cumulative_contributions AS (
                SELECT
                    employee_id,
                    SUM(COALESCE(total_employer_contributions, 0))
                        AS total_employer_contributions
                FROM fct_workforce_snapshot
                WHERE simulation_year < ?
                  AND UPPER(employment_status) = 'ACTIVE'
                GROUP BY employee_id
            )
            SELECT
                t.employee_id,
                t.employee_hire_date,
                t.termination_date,
                t.current_tenure,
                t.tenure_band,
                COALESCE(p.total_employer_contributions, 0) as total_employer_contributions,
                t.annual_hours_worked
            FROM terminated_this_year t
            LEFT JOIN cumulative_contributions p
              ON t.employee_id = p.employee_id
            WHERE COALESCE(p.total_employer_contributions, 0) > 0
            ORDER BY p.total_employer_contributions DESC
        """
        result = conn.execute(query, [year, year]).fetchall()
        columns = [
            "employee_id",
            "employee_hire_date",
            "termination_date",
            "current_tenure",
            "tenure_band",
            "total_employer_contributions",
            "annual_hours_worked",
        ]
        return [dict(zip(columns, row)) for row in result]

    def _get_total_terminated_employee_count(self, conn, year: int) -> int:
        """Count all employees terminated in the selected analysis year."""
        result = conn.execute(
            """
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
              AND UPPER(employment_status) = 'TERMINATED'
            """,
            [year],
        ).fetchone()
        return int(result[0]) if result else 0

    def _calculate_employee_details(
        self,
        employees: List[dict],
        current_schedule: VestingScheduleConfig,
        proposed_schedule: VestingScheduleConfig,
    ) -> List[EmployeeVestingDetail]:
        """Calculate vesting details for each employee (T026)."""
        details = []
        for emp in employees:
            tenure = emp["current_tenure"] or 0
            contributions = Decimal(str(emp["total_employer_contributions"]))
            hours = emp["annual_hours_worked"] or 0

            # Calculate current schedule vesting
            current_pct = get_vesting_percentage(
                current_schedule.schedule_type,
                tenure,
                hours,
                current_schedule.require_hours_credit,
                current_schedule.hours_threshold,
            )
            current_vested = (contributions * current_pct).quantize(Decimal("0.01"))
            current_forfeiture = calculate_forfeiture(contributions, current_pct)

            # Calculate proposed schedule vesting
            proposed_pct = get_vesting_percentage(
                proposed_schedule.schedule_type,
                tenure,
                hours,
                proposed_schedule.require_hours_credit,
                proposed_schedule.hours_threshold,
            )
            proposed_vested = (contributions * proposed_pct).quantize(Decimal("0.01"))
            proposed_forfeiture = calculate_forfeiture(contributions, proposed_pct)

            # Variance (positive = proposed has more forfeiture)
            variance = proposed_forfeiture - current_forfeiture

            detail = EmployeeVestingDetail(
                employee_id=emp["employee_id"],
                hire_date=emp["employee_hire_date"].date()
                if hasattr(emp["employee_hire_date"], "date")
                else emp["employee_hire_date"],
                termination_date=emp["termination_date"].date()
                if hasattr(emp["termination_date"], "date")
                else emp["termination_date"],
                tenure_years=int(tenure),
                tenure_band=emp["tenure_band"] or "Unknown",
                annual_hours_worked=hours,
                total_employer_contributions=contributions,
                current_vesting_pct=current_pct,
                current_vested_amount=current_vested,
                current_forfeiture=current_forfeiture,
                proposed_vesting_pct=proposed_pct,
                proposed_vested_amount=proposed_vested,
                proposed_forfeiture=proposed_forfeiture,
                forfeiture_variance=variance,
            )
            details.append(detail)

        return details

    def _build_summary(
        self,
        details: List[EmployeeVestingDetail],
        year: int,
        total_terminated_employee_count: int,
    ) -> VestingAnalysisSummary:
        """Build summary statistics from employee details (T027)."""
        if not details:
            return VestingAnalysisSummary(
                analysis_year=year,
                total_terminated_employee_count=total_terminated_employee_count,
                vesting_eligible_terminated_employee_count=0,
                terminated_employee_count=0,
                total_employer_contributions=Decimal("0"),
                current_total_vested=Decimal("0"),
                current_total_forfeited=Decimal("0"),
                proposed_total_vested=Decimal("0"),
                proposed_total_forfeited=Decimal("0"),
                forfeiture_variance=Decimal("0"),
                forfeiture_variance_pct=Decimal("0"),
            )

        total_contributions = sum(d.total_employer_contributions for d in details)
        current_vested = sum(d.current_vested_amount for d in details)
        current_forfeited = sum(d.current_forfeiture for d in details)
        proposed_vested = sum(d.proposed_vested_amount for d in details)
        proposed_forfeited = sum(d.proposed_forfeiture for d in details)
        variance = proposed_forfeited - current_forfeited

        # Calculate percentage change
        if current_forfeited > 0:
            variance_pct = Decimal(variance / current_forfeited * 100).quantize(
                Decimal("0.01")
            )
        else:
            variance_pct = Decimal("0") if variance == 0 else Decimal("100")

        return VestingAnalysisSummary(
            analysis_year=year,
            total_terminated_employee_count=total_terminated_employee_count,
            vesting_eligible_terminated_employee_count=len(details),
            terminated_employee_count=len(details),
            total_employer_contributions=total_contributions,
            current_total_vested=current_vested,
            current_total_forfeited=current_forfeited,
            proposed_total_vested=proposed_vested,
            proposed_total_forfeited=proposed_forfeited,
            forfeiture_variance=variance,
            forfeiture_variance_pct=variance_pct,
        )

    def _tenure_band_sort_key(self, band: str) -> int:
        """Extract numeric sort key from tenure band string.

        Handles formats like: '<2', '2-4', '5-9', '10-19', '20+'
        """
        import re

        # Extract first number from the band string
        match = re.search(r"\d+", band)
        if match:
            return int(match.group())
        # '<2' or similar - sort first
        if "<" in band:
            return 0
        return 999  # Unknown format goes last

    def _aggregate_by_tenure_band(
        self, details: List[EmployeeVestingDetail]
    ) -> List[TenureBandSummary]:
        """Aggregate forfeitures by tenure band (T028)."""
        bands: dict[str, dict] = {}
        for d in details:
            band = d.tenure_band
            if band not in bands:
                bands[band] = {
                    "employee_count": 0,
                    "total_contributions": Decimal("0"),
                    "current_forfeitures": Decimal("0"),
                    "proposed_forfeitures": Decimal("0"),
                }
            bands[band]["employee_count"] += 1
            bands[band]["total_contributions"] += d.total_employer_contributions
            bands[band]["current_forfeitures"] += d.current_forfeiture
            bands[band]["proposed_forfeitures"] += d.proposed_forfeiture

        return [
            TenureBandSummary(
                tenure_band=band,
                employee_count=data["employee_count"],
                total_contributions=data["total_contributions"],
                current_forfeitures=data["current_forfeitures"],
                proposed_forfeitures=data["proposed_forfeitures"],
                forfeiture_variance=data["proposed_forfeitures"]
                - data["current_forfeitures"],
            )
            for band, data in sorted(
                bands.items(), key=lambda x: self._tenure_band_sort_key(x[0])
            )
        ]

    def _get_terminated_employees_all_years(self, conn) -> List[dict]:
        """Every contribution-qualified termination, all years, in one query."""
        return _terminated_employees_all_years(conn)

    def _get_terminated_counts_by_year(self, conn) -> dict[int, int]:
        """All terminations per year, regardless of contribution basis."""
        return _terminated_counts_by_year(conn)

    def _get_simulation_years(self, conn) -> List[int]:
        return _simulation_years(conn)

    def _forfeiture_row(
        self,
        year: int,
        employees: List[dict],
        terminated_count: int,
        schedule: VestingScheduleConfig,
        has_prior_year_basis: bool,
    ) -> ForfeitureYearRow:
        """Apply one schedule to one year's qualified terminations."""
        return _forfeiture_row(
            year, employees, terminated_count, schedule, has_prior_year_basis
        )

    def _build_scenario_series(
        self,
        scenario_id: str,
        scenario_name: str,
        conn,
        schedule: VestingScheduleConfig,
        policy: ForfeiturePolicy,
    ) -> Optional[ScenarioForfeitureSeries]:
        """Build one scenario's full year series, or None if it has no years."""
        rows = project_forfeitures_for_connection(conn, schedule)
        if not rows:
            return None

        return ScenarioForfeitureSeries(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            years=rows,
            total_employer_contributions=sum(
                (row.total_employer_contributions for row in rows), Decimal("0")
            ),
            total_vested=sum((row.vested_amount for row in rows), Decimal("0")),
            total_forfeited=sum((row.forfeited_amount for row in rows), Decimal("0")),
            employer_cost_offsets=build_employer_cost_offsets(rows, policy),
        )

    def project_forfeitures(
        self,
        workspace_id: str,
        scenarios: List[tuple[str, str]],
        schedule: VestingScheduleConfig,
        policy: ForfeiturePolicy = ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
    ) -> ForfeitureProjectionResponse:
        """Forfeitures under one schedule, every year, across several scenarios.

        A scenario whose database is missing or empty is skipped with a reason
        rather than failing the whole request. Each series also carries the
        per-year employer cost offsets implied by ``policy`` (#444), so the
        Cost Comparison page never has to re-implement the policy semantics.
        """
        import duckdb

        series: List[ScenarioForfeitureSeries] = []
        skipped: List[SkippedScenario] = []

        for scenario_id, scenario_name in scenarios:
            resolved = self.db_resolver.resolve(workspace_id, scenario_id)
            if not resolved.exists:
                logger.warning(
                    f"Skipping {scenario_id}: database not found at {resolved.path}"
                )
                skipped.append(
                    SkippedScenario(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        reason="Simulation database not found for this scenario",
                    )
                )
                continue

            conn = duckdb.connect(str(resolved.path), read_only=True)
            try:
                built = self._build_scenario_series(
                    scenario_id, scenario_name, conn, schedule, policy
                )
            finally:
                conn.close()

            if built is None:
                skipped.append(
                    SkippedScenario(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        reason="Scenario database contains no simulation years",
                    )
                )
                continue
            series.append(built)

        all_years = sorted(
            {row.simulation_year for item in series for row in item.years}
        )
        return ForfeitureProjectionResponse(
            schedule=schedule,
            forfeiture_policy=policy,
            years=all_years,
            scenarios=series,
            skipped=skipped,
        )

    def analyze_vesting(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        request: VestingAnalysisRequest,
    ) -> Optional[VestingAnalysisResponse]:
        """Run vesting analysis comparing two schedules (T029)."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            logger.error(f"Database not found for scenario {scenario_id}")
            return None

        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            # Get final year if not specified
            year = request.simulation_year or self._get_final_year(conn)

            total_terminated_employee_count = self._get_total_terminated_employee_count(
                conn, year
            )

            # Query terminated employees with prior-year employer contributions.
            employees = self._get_terminated_employees(conn, year)

            if not employees:
                logger.info(f"No terminated employees found for year {year}")
                # Return empty response
                return VestingAnalysisResponse(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    current_schedule=request.current_schedule,
                    proposed_schedule=request.proposed_schedule,
                    summary=self._build_summary(
                        [], year, total_terminated_employee_count
                    ),
                    by_tenure_band=[],
                    employee_details=[],
                )

            # Calculate vesting for each employee
            details = self._calculate_employee_details(
                employees, request.current_schedule, request.proposed_schedule
            )

            # Aggregate results
            summary = self._build_summary(
                details, year, total_terminated_employee_count
            )
            by_tenure_band = self._aggregate_by_tenure_band(details)

            return VestingAnalysisResponse(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                current_schedule=request.current_schedule,
                proposed_schedule=request.proposed_schedule,
                summary=summary,
                by_tenure_band=by_tenure_band,
                employee_details=details,
            )
        finally:
            conn.close()
