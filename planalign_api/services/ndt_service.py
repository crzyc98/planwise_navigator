"""NDT (Non-Discrimination Testing) service for ACP test computation."""

import logging
from typing import List, Optional

from pydantic import BaseModel

from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver

logger = logging.getLogger(__name__)


# ==============================================================================
# Pydantic Response Models
# ==============================================================================


class ACPEmployeeDetail(BaseModel):
    employee_id: str
    is_hce: bool
    is_enrolled: bool
    employer_match_amount: float
    eligible_compensation: float
    individual_acp: float
    prior_year_compensation: Optional[float] = None


class ACPScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str  # "pass", "fail", "error"
    test_message: Optional[str] = None
    hce_count: int = 0
    nhce_count: int = 0
    excluded_count: int = 0
    eligible_not_enrolled_count: int = 0
    hce_average_acp: float = 0.0
    nhce_average_acp: float = 0.0
    basic_test_threshold: float = 0.0
    alternative_test_threshold: float = 0.0
    applied_test: str = "basic"  # "basic" or "alternative"
    applied_threshold: float = 0.0
    margin: float = 0.0
    hce_threshold_used: int = 0
    employees: Optional[List[ACPEmployeeDetail]] = None


class ACPTestResponse(BaseModel):
    test_type: str = "acp"
    year: int
    results: List[ACPScenarioResult]


class AvailableYearsResponse(BaseModel):
    years: List[int]
    default_year: Optional[int] = None


# ==============================================================================
# NDT Service
# ==============================================================================


class NDTService:
    """Service for Non-Discrimination Testing analytics."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def get_available_years(
        self, workspace_id: str, scenario_id: str
    ) -> AvailableYearsResponse:
        """Get available simulation years for NDT testing."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return AvailableYearsResponse(years=[], default_year=None)

        try:
            conn = duckdb.connect(str(resolved.path), read_only=True)
            result = conn.execute(
                "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year"
            ).fetchall()
            conn.close()

            years = [row[0] for row in result]
            default_year = years[-1] if years else None
            return AvailableYearsResponse(years=years, default_year=default_year)
        except Exception as e:
            logger.error(f"Failed to get available years: {e}")
            return AvailableYearsResponse(years=[], default_year=None)

    def run_acp_test(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        year: int,
        include_employees: bool = False,
    ) -> ACPScenarioResult:
        """Run the ACP non-discrimination test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return ACPScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        try:
            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Check if HCE threshold exists for the determination year
            hce_threshold_row = conn.execute(
                "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                [year - 1],
            ).fetchone()

            if not hce_threshold_row or hce_threshold_row[0] is None:
                # Fallback: try current year threshold
                hce_threshold_row = conn.execute(
                    "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                    [year],
                ).fetchone()
                if not hce_threshold_row or hce_threshold_row[0] is None:
                    conn.close()
                    return ACPScenarioResult(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        simulation_year=year,
                        test_result="error",
                        test_message=f"HCE compensation threshold not found in config_irs_limits for year {year - 1} or {year}. Please add the hce_compensation_threshold column to the IRS limits seed.",
                    )

            hce_threshold = int(hce_threshold_row[0])

            # Check if prior year data exists
            prior_year_exists = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year - 1],
            ).fetchone()[0] > 0

            # Main ACP query with HCE determination
            query = """
            WITH prior_year AS (
                SELECT employee_id, current_compensation AS prior_year_comp
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
            ),
            current_year AS (
                SELECT
                    s.employee_id,
                    s.current_eligibility_status,
                    s.is_enrolled_flag,
                    s.employer_match_amount,
                    s.prorated_annual_compensation,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                WHERE s.simulation_year = ?
                  AND s.current_eligibility_status = 'eligible'
                  AND s.prorated_annual_compensation > 0
            ),
            per_employee AS (
                SELECT *,
                    COALESCE(employer_match_amount, 0) / prorated_annual_compensation AS individual_acp
                FROM current_year
            )
            SELECT
                employee_id,
                is_hce,
                is_enrolled_flag,
                COALESCE(employer_match_amount, 0) AS employer_match_amount,
                prorated_annual_compensation AS eligible_compensation,
                individual_acp,
                prior_year_comp
            FROM per_employee
            ORDER BY is_hce DESC, individual_acp DESC
            """

            prior_year_param = year - 1 if prior_year_exists else year
            rows = conn.execute(query, [prior_year_param, hce_threshold, year]).fetchall()
            conn.close()

            if not rows:
                return ACPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="No eligible employees found for ACP test",
                )

            # Compute group averages
            hce_acps = []
            nhce_acps = []
            employees = []
            eligible_not_enrolled = 0

            for row in rows:
                emp_id, is_hce, is_enrolled, match_amt, comp, acp, prior_comp = row
                if is_hce:
                    hce_acps.append(acp)
                else:
                    nhce_acps.append(acp)
                if not is_enrolled:
                    eligible_not_enrolled += 1
                if include_employees:
                    employees.append(ACPEmployeeDetail(
                        employee_id=str(emp_id),
                        is_hce=bool(is_hce),
                        is_enrolled=bool(is_enrolled),
                        employer_match_amount=float(match_amt),
                        eligible_compensation=float(comp),
                        individual_acp=float(acp),
                        prior_year_compensation=float(prior_comp) if prior_comp is not None else None,
                    ))

            # Edge case: no NHCE employees
            if not nhce_acps:
                return ACPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="Insufficient NHCE population",
                    hce_count=len(hce_acps),
                    nhce_count=0,
                    hce_threshold_used=hce_threshold,
                    employees=employees if include_employees else None,
                )

            # Edge case: no HCE employees -> auto-pass
            if not hce_acps:
                nhce_avg = sum(nhce_acps) / len(nhce_acps)
                return ACPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No HCE employees in population",
                    hce_count=0,
                    nhce_count=len(nhce_acps),
                    hce_average_acp=0.0,
                    nhce_average_acp=nhce_avg,
                    hce_threshold_used=hce_threshold,
                    eligible_not_enrolled_count=eligible_not_enrolled,
                    employees=employees if include_employees else None,
                )

            # Compute pass/fail
            return self._compute_test_result(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                year=year,
                hce_acps=hce_acps,
                nhce_acps=nhce_acps,
                hce_threshold=hce_threshold,
                eligible_not_enrolled=eligible_not_enrolled,
                excluded_count=0,
                employees=employees if include_employees else None,
            )

        except Exception as e:
            logger.error(f"Failed to run ACP test: {e}")
            return ACPScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=str(e),
            )

    def _compute_test_result(
        self,
        scenario_id: str,
        scenario_name: str,
        year: int,
        hce_acps: List[float],
        nhce_acps: List[float],
        hce_threshold: int,
        eligible_not_enrolled: int,
        excluded_count: int,
        employees: Optional[List[ACPEmployeeDetail]],
    ) -> ACPScenarioResult:
        """Compute IRS ACP test pass/fail using basic and alternative tests."""
        hce_avg = sum(hce_acps) / len(hce_acps)
        nhce_avg = sum(nhce_acps) / len(nhce_acps)

        # Basic test: NHCE avg x 1.25
        basic_threshold = nhce_avg * 1.25

        # Alternative test: lesser of (NHCE avg x 2.0) and (NHCE avg + 0.02)
        alt_threshold = min(nhce_avg * 2.0, nhce_avg + 0.02)

        # Select more favorable test (higher threshold)
        if basic_threshold >= alt_threshold:
            applied_test = "basic"
            applied_threshold = basic_threshold
        else:
            applied_test = "alternative"
            applied_threshold = alt_threshold

        # Determine pass/fail
        test_result = "pass" if hce_avg <= applied_threshold else "fail"
        margin = applied_threshold - hce_avg

        return ACPScenarioResult(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            simulation_year=year,
            test_result=test_result,
            hce_count=len(hce_acps),
            nhce_count=len(nhce_acps),
            excluded_count=excluded_count,
            eligible_not_enrolled_count=eligible_not_enrolled,
            hce_average_acp=hce_avg,
            nhce_average_acp=nhce_avg,
            basic_test_threshold=basic_threshold,
            alternative_test_threshold=alt_threshold,
            applied_test=applied_test,
            applied_threshold=applied_threshold,
            margin=margin,
            hce_threshold_used=hce_threshold,
            employees=employees,
        )
