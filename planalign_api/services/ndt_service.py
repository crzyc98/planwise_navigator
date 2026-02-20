"""NDT (Non-Discrimination Testing) service for ACP, ADP, 401(a)(4), and 415 tests."""

import logging
import statistics
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydantic import BaseModel

from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver, IsolationMode

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
# 401(a)(4) General Test Response Models
# ==============================================================================


class Section401a4EmployeeDetail(BaseModel):
    employee_id: str
    is_hce: bool
    employer_nec_amount: float = 0.0
    employer_match_amount: float = 0.0
    total_employer_amount: float = 0.0
    plan_compensation: float = 0.0
    contribution_rate: float = 0.0
    years_of_service: float = 0.0


class Section401a4ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str  # "pass", "fail", "error"
    test_message: Optional[str] = None
    applied_test: str = "ratio"  # "ratio" or "general"
    hce_count: int = 0
    nhce_count: int = 0
    excluded_count: int = 0
    hce_average_rate: float = 0.0
    nhce_average_rate: float = 0.0
    hce_median_rate: float = 0.0
    nhce_median_rate: float = 0.0
    ratio: float = 0.0
    ratio_test_threshold: float = 0.70
    margin: float = 0.0
    include_match: bool = False
    service_risk_flag: bool = False
    service_risk_detail: Optional[str] = None
    hce_threshold_used: int = 0
    employees: Optional[List[Section401a4EmployeeDetail]] = None


class Section401a4TestResponse(BaseModel):
    test_type: str = "401a4"
    year: int
    results: List[Section401a4ScenarioResult]


# ==============================================================================
# 415 Annual Additions Limit Test Response Models
# ==============================================================================


class Section415EmployeeDetail(BaseModel):
    employee_id: str
    status: str  # "pass", "at_risk", "breach"
    employee_deferrals: float = 0.0
    employer_match: float = 0.0
    employer_nec: float = 0.0
    total_annual_additions: float = 0.0
    gross_compensation: float = 0.0
    applicable_limit: float = 0.0
    headroom: float = 0.0
    utilization_pct: float = 0.0


class Section415ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str  # "pass", "fail", "error"
    test_message: Optional[str] = None
    total_participants: int = 0
    excluded_count: int = 0
    breach_count: int = 0
    at_risk_count: int = 0
    passing_count: int = 0
    max_utilization_pct: float = 0.0
    warning_threshold_pct: float = 0.95
    annual_additions_limit: int = 0
    employees: Optional[List[Section415EmployeeDetail]] = None


class Section415TestResponse(BaseModel):
    test_type: str = "415"
    year: int
    results: List[Section415ScenarioResult]


# ==============================================================================
# ADP (Actual Deferral Percentage) Test Response Models
# ==============================================================================


class ADPEmployeeDetail(BaseModel):
    employee_id: str
    is_hce: bool
    employee_deferrals: float
    plan_compensation: float
    individual_adp: float
    prior_year_compensation: Optional[float] = None


class ADPScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str  # "pass", "fail", "exempt", "error"
    test_message: Optional[str] = None
    hce_count: int = 0
    nhce_count: int = 0
    excluded_count: int = 0
    hce_average_adp: float = 0.0
    nhce_average_adp: float = 0.0
    basic_test_threshold: float = 0.0
    alternative_test_threshold: float = 0.0
    applied_test: str = "basic"  # "basic" or "alternative"
    applied_threshold: float = 0.0
    margin: float = 0.0
    excess_hce_amount: Optional[float] = None
    testing_method: str = "current"  # "current" or "prior"
    safe_harbor: bool = False
    hce_threshold_used: int = 0
    employees: Optional[List[ADPEmployeeDetail]] = None


class ADPTestResponse(BaseModel):
    test_type: str = "adp"
    year: int
    results: List[ADPScenarioResult]


# ==============================================================================
# NDT Service
# ==============================================================================


class NDTService:
    """Service for Non-Discrimination Testing analytics."""

    # Path to dbt seeds directory
    _SEEDS_DIR = Path(__file__).resolve().parents[2] / "dbt" / "seeds"

    # Per-path lock to serialize seed checks and avoid racing with readers
    _seed_lock_guard: threading.Lock = threading.Lock()
    _seed_locks: Dict[str, threading.Lock] = {}
    _seed_verified: Set[str] = set()

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(
            storage, isolation_mode=IsolationMode.MULTI_TENANT
        )

    @staticmethod
    def _get_seed_lock(db_path: Path) -> threading.Lock:
        """Get or create a per-path lock for seed operations."""
        key = str(db_path)
        with NDTService._seed_lock_guard:
            if key not in NDTService._seed_locks:
                NDTService._seed_locks[key] = threading.Lock()
            return NDTService._seed_locks[key]

    @staticmethod
    def _ensure_seed_current(db_path: Path) -> None:
        """Ensure config_irs_limits seed table has required columns.

        Thread-safe: uses a per-path lock so concurrent requests don't
        race on DROP/CREATE, and caches verification so the check runs
        at most once per database path per process lifetime.
        """
        import duckdb

        key = str(db_path)

        # Fast path: already verified this database, no lock needed
        if key in NDTService._seed_verified:
            return

        csv_path = NDTService._SEEDS_DIR / "config_irs_limits.csv"
        if not csv_path.exists():
            logger.warning(f"Seed CSV not found: {csv_path}")
            return

        lock = NDTService._get_seed_lock(db_path)
        with lock:
            # Re-check after acquiring lock (another thread may have finished)
            if key in NDTService._seed_verified:
                return

            required_columns = (
                'hce_compensation_threshold',
                'super_catch_up_limit',
                'annual_additions_limit',
            )
            conn = duckdb.connect(str(db_path))
            try:
                # Check if all required columns exist
                column_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = 'main'
                      AND table_name = 'config_irs_limits'
                      AND column_name IN (?, ?, ?)
                    """,
                    list(required_columns),
                ).fetchone()[0]

                if column_count == len(required_columns):
                    NDTService._seed_verified.add(key)
                    return  # Already up to date

                # Column(s) missing — reload the seed table from CSV
                missing = []
                for col in required_columns:
                    has = conn.execute(
                        """
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'main'
                          AND table_name = 'config_irs_limits'
                          AND column_name = ?
                        LIMIT 1
                        """,
                        [col],
                    ).fetchone()
                    if not has:
                        missing.append(col)

                logger.info(
                    f"config_irs_limits missing column(s): {missing}, "
                    "reloading seed from CSV"
                )
                conn.execute("DROP TABLE IF EXISTS config_irs_limits")
                conn.execute(
                    f"""
                    CREATE TABLE config_irs_limits AS
                    SELECT * FROM read_csv_auto('{csv_path}')
                    """
                )
                logger.info("config_irs_limits seed reloaded successfully")
                NDTService._seed_verified.add(key)
            except Exception as e:
                logger.error(f"Failed to ensure seed current: {e}")
            finally:
                conn.close()

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
            # Ensure seed table has the hce_compensation_threshold column
            self._ensure_seed_current(resolved.path)

            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Get HCE threshold for the prior year (used for HCE determination)
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
                        test_message=f"HCE compensation threshold not found in config_irs_limits for year {year - 1} or {year}.",
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
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
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

    # ==================================================================
    # 401(a)(4) General Nondiscrimination Test
    # ==================================================================

    def run_401a4_test(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        year: int,
        include_employees: bool = False,
        include_match: bool = False,
    ) -> Section401a4ScenarioResult:
        """Run the 401(a)(4) general nondiscrimination test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return Section401a4ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        try:
            self._ensure_seed_current(resolved.path)
            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Get HCE threshold for the prior year
            hce_threshold_row = conn.execute(
                "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                [year - 1],
            ).fetchone()
            if not hce_threshold_row or hce_threshold_row[0] is None:
                hce_threshold_row = conn.execute(
                    "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                    [year],
                ).fetchone()
                if not hce_threshold_row or hce_threshold_row[0] is None:
                    conn.close()
                    return Section401a4ScenarioResult(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        simulation_year=year,
                        test_result="error",
                        test_message=f"HCE compensation threshold not found for year {year - 1} or {year}.",
                    )

            hce_threshold = int(hce_threshold_row[0])

            # Check prior year data
            prior_year_exists = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year - 1],
            ).fetchone()[0] > 0

            prior_year_param = year - 1 if prior_year_exists else year

            # Main query for 401(a)(4) test
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
                    s.prorated_annual_compensation,
                    COALESCE(s.employer_core_amount, 0) AS employer_core_amount,
                    COALESCE(s.employer_match_amount, 0) AS employer_match_amount,
                    s.current_tenure,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                WHERE s.simulation_year = ?
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
            )
            SELECT
                employee_id,
                is_hce,
                employer_core_amount,
                employer_match_amount,
                prorated_annual_compensation,
                current_tenure
            FROM current_year
            WHERE (employer_core_amount > 0 OR employer_match_amount > 0)
            ORDER BY is_hce DESC
            """

            rows = conn.execute(query, [prior_year_param, hce_threshold, year]).fetchall()
            conn.close()

            if not rows:
                return Section401a4ScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="No eligible employees found for 401(a)(4) test",
                    hce_threshold_used=hce_threshold,
                )

            # Process rows
            hce_rates: List[float] = []
            nhce_rates: List[float] = []
            hce_tenures: List[float] = []
            nhce_tenures: List[float] = []
            employees: List[Section401a4EmployeeDetail] = []
            excluded_count = 0

            for row in rows:
                emp_id, is_hce, core_amt, match_amt, plan_comp, tenure = row

                if plan_comp is None or plan_comp <= 0:
                    excluded_count += 1
                    continue

                if include_match:
                    total_employer = core_amt + match_amt
                else:
                    total_employer = core_amt

                rate = total_employer / plan_comp

                if is_hce:
                    hce_rates.append(rate)
                    hce_tenures.append(float(tenure or 0))
                else:
                    nhce_rates.append(rate)
                    nhce_tenures.append(float(tenure or 0))

                if include_employees:
                    employees.append(Section401a4EmployeeDetail(
                        employee_id=str(emp_id),
                        is_hce=bool(is_hce),
                        employer_nec_amount=float(core_amt),
                        employer_match_amount=float(match_amt) if include_match else 0.0,
                        total_employer_amount=float(total_employer),
                        plan_compensation=float(plan_comp),
                        contribution_rate=float(rate),
                        years_of_service=float(tenure or 0),
                    ))

            # Edge case: no NHCE employees
            if not nhce_rates:
                return Section401a4ScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No NHCE employees in population — auto-pass",
                    hce_count=len(hce_rates),
                    nhce_count=0,
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )

            # Edge case: no HCE employees -> auto-pass
            if not hce_rates:
                return Section401a4ScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No HCE employees in population — auto-pass",
                    hce_count=0,
                    nhce_count=len(nhce_rates),
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )

            # Edge case: no employer contributions at all
            if all(r == 0.0 for r in hce_rates) and all(r == 0.0 for r in nhce_rates):
                return Section401a4ScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No employer contributions — test not applicable",
                    hce_count=len(hce_rates),
                    nhce_count=len(nhce_rates),
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )

            # Compute pass/fail
            result = self._compute_401a4_result(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                year=year,
                hce_rates=hce_rates,
                nhce_rates=nhce_rates,
                hce_threshold=hce_threshold,
                excluded_count=excluded_count,
                include_match=include_match,
                employees=employees if include_employees else None,
            )

            # Service-based risk detection (T008)
            self._detect_service_risk(
                result, workspace_id, scenario_id, hce_tenures, nhce_tenures
            )

            return result

        except Exception as e:
            logger.error(f"Failed to run 401(a)(4) test: {e}")
            return Section401a4ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=str(e),
            )

    def _compute_401a4_result(
        self,
        scenario_id: str,
        scenario_name: str,
        year: int,
        hce_rates: List[float],
        nhce_rates: List[float],
        hce_threshold: int,
        excluded_count: int,
        include_match: bool,
        employees: Optional[List[Section401a4EmployeeDetail]],
    ) -> Section401a4ScenarioResult:
        """Compute 401(a)(4) pass/fail using ratio test with general test fallback."""
        hce_avg = sum(hce_rates) / len(hce_rates)
        nhce_avg = sum(nhce_rates) / len(nhce_rates)
        hce_median = statistics.median(hce_rates)
        nhce_median = statistics.median(nhce_rates)

        # Ratio test: nhce_avg / hce_avg >= 0.70
        ratio = nhce_avg / hce_avg if hce_avg > 0 else 1.0

        if ratio >= 0.70:
            applied_test = "ratio"
            margin = ratio - 0.70
            test_result = "pass"
        else:
            # General test fallback: nhce_median / hce_median >= 0.70
            median_ratio = nhce_median / hce_median if hce_median > 0 else 1.0
            if median_ratio >= 0.70:
                applied_test = "general"
                margin = median_ratio - 0.70
                test_result = "pass"
            else:
                applied_test = "general"
                margin = median_ratio - 0.70
                test_result = "fail"

        return Section401a4ScenarioResult(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            simulation_year=year,
            test_result=test_result,
            applied_test=applied_test,
            hce_count=len(hce_rates),
            nhce_count=len(nhce_rates),
            excluded_count=excluded_count,
            hce_average_rate=hce_avg,
            nhce_average_rate=nhce_avg,
            hce_median_rate=hce_median,
            nhce_median_rate=nhce_median,
            ratio=ratio,
            margin=margin,
            include_match=include_match,
            hce_threshold_used=hce_threshold,
            employees=employees,
        )

    def _detect_service_risk(
        self,
        result: Section401a4ScenarioResult,
        workspace_id: str,
        scenario_id: str,
        hce_tenures: List[float],
        nhce_tenures: List[float],
    ) -> None:
        """Detect service-based NEC tenure skew risk (mutates result in-place)."""
        try:
            config = self.storage.get_merged_config(workspace_id, scenario_id)
            if not config:
                return
            ec_config = config.get("employer_core_contribution", {})
            if not isinstance(ec_config, dict):
                return
            ec_status = ec_config.get("status", "")

            if ec_status == "graded_by_service" and hce_tenures and nhce_tenures:
                hce_avg_tenure = sum(hce_tenures) / len(hce_tenures)
                nhce_avg_tenure = sum(nhce_tenures) / len(nhce_tenures)
                tenure_diff = hce_avg_tenure - nhce_avg_tenure

                if tenure_diff > 3.0:
                    result.service_risk_flag = True
                    result.service_risk_detail = (
                        f"HCE avg tenure: {hce_avg_tenure:.1f} yrs, "
                        f"NHCE avg tenure: {nhce_avg_tenure:.1f} yrs"
                    )
        except Exception as e:
            logger.debug(f"Service risk detection skipped: {e}")

    # ==================================================================
    # 415 Annual Additions Limit Test
    # ==================================================================

    def run_415_test(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        year: int,
        include_employees: bool = False,
        warning_threshold: float = 0.95,
    ) -> Section415ScenarioResult:
        """Run the Section 415 annual additions limit test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return Section415ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        try:
            self._ensure_seed_current(resolved.path)
            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Get IRS limits for the test year
            limits_row = conn.execute(
                "SELECT annual_additions_limit, base_limit FROM config_irs_limits WHERE limit_year = ?",
                [year],
            ).fetchone()

            if not limits_row or limits_row[0] is None or limits_row[1] is None:
                conn.close()
                return Section415ScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message=f"IRS limits not found in config_irs_limits for year {year}",
                )

            annual_additions_limit = int(limits_row[0])
            base_limit = int(limits_row[1])

            # Query eligible participants
            query = """
            SELECT
                employee_id,
                current_compensation,
                prorated_annual_compensation,
                COALESCE(prorated_annual_contributions, 0) AS contributions,
                COALESCE(employer_match_amount, 0) AS match_amount,
                COALESCE(employer_core_amount, 0) AS core_amount
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
              AND (current_eligibility_status = 'eligible' OR current_eligibility_status IS NULL)
            """

            rows = conn.execute(query, [year]).fetchall()
            conn.close()

            # Process participants
            employees: List[Section415EmployeeDetail] = []
            breach_count = 0
            at_risk_count = 0
            passing_count = 0
            excluded_count = 0
            max_utilization = 0.0

            for row in rows:
                emp_id, gross_comp, prorated_comp, contributions, match_amt, core_amt = row

                if gross_comp is None or gross_comp <= 0:
                    excluded_count += 1
                    continue

                # Base deferrals = min(contributions, base_limit) — excludes catch-up
                base_deferrals = min(float(contributions), float(base_limit))

                # Total annual additions
                total_additions = base_deferrals + float(match_amt) + float(core_amt)

                # Applicable 415 limit = lesser of IRS dollar limit or 100% of gross comp
                applicable_limit = min(float(annual_additions_limit), float(gross_comp))

                headroom = applicable_limit - total_additions
                utilization = total_additions / applicable_limit if applicable_limit > 0 else 0.0
                max_utilization = max(max_utilization, utilization)

                # Classify
                if total_additions > applicable_limit:
                    emp_status = "breach"
                    breach_count += 1
                elif utilization >= warning_threshold:
                    emp_status = "at_risk"
                    at_risk_count += 1
                else:
                    emp_status = "pass"
                    passing_count += 1

                if include_employees:
                    employees.append(Section415EmployeeDetail(
                        employee_id=str(emp_id),
                        status=emp_status,
                        employee_deferrals=base_deferrals,
                        employer_match=float(match_amt),
                        employer_nec=float(core_amt),
                        total_annual_additions=total_additions,
                        gross_compensation=float(gross_comp),
                        applicable_limit=applicable_limit,
                        headroom=headroom,
                        utilization_pct=utilization,
                    ))

            total_participants = breach_count + at_risk_count + passing_count
            test_result = "fail" if breach_count > 0 else "pass"

            return Section415ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result=test_result,
                total_participants=total_participants,
                excluded_count=excluded_count,
                breach_count=breach_count,
                at_risk_count=at_risk_count,
                passing_count=passing_count,
                max_utilization_pct=max_utilization,
                warning_threshold_pct=warning_threshold,
                annual_additions_limit=annual_additions_limit,
                employees=employees if include_employees else None,
            )

        except Exception as e:
            logger.error(f"Failed to run 415 test: {e}")
            return Section415ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=str(e),
            )

    # ==================================================================
    # ADP (Actual Deferral Percentage) Test
    # ==================================================================

    def run_adp_test(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        year: int,
        include_employees: bool = False,
        safe_harbor: bool = False,
        testing_method: str = "current",
    ) -> ADPScenarioResult:
        """Run the ADP non-discrimination test for a single scenario and year."""
        import duckdb

        # Safe harbor short-circuit
        if safe_harbor:
            return ADPScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="exempt",
                test_message="Safe harbor plan — ADP test not required",
                safe_harbor=True,
                testing_method=testing_method,
            )

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return ADPScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
                testing_method=testing_method,
            )

        try:
            self._ensure_seed_current(resolved.path)
            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Get HCE threshold for the prior year
            hce_threshold_row = conn.execute(
                "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                [year - 1],
            ).fetchone()

            if not hce_threshold_row or hce_threshold_row[0] is None:
                hce_threshold_row = conn.execute(
                    "SELECT hce_compensation_threshold FROM config_irs_limits WHERE limit_year = ?",
                    [year],
                ).fetchone()
                if not hce_threshold_row or hce_threshold_row[0] is None:
                    conn.close()
                    return ADPScenarioResult(
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        simulation_year=year,
                        test_result="error",
                        test_message=f"HCE compensation threshold not found in config_irs_limits for year {year - 1} or {year}.",
                        testing_method=testing_method,
                    )

            hce_threshold = int(hce_threshold_row[0])

            # Check if prior year data exists
            prior_year_exists = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year - 1],
            ).fetchone()[0] > 0

            # Prior year testing method: get NHCE ADP from prior year
            prior_year_nhce_adp = None
            actual_testing_method = testing_method
            if testing_method == "prior":
                if prior_year_exists:
                    prior_nhce_query = """
                    WITH prior_hce AS (
                        SELECT employee_id, current_compensation AS comp
                        FROM fct_workforce_snapshot
                        WHERE simulation_year = ?
                    ),
                    prior_data AS (
                        SELECT
                            s.employee_id,
                            COALESCE(s.prorated_annual_contributions, 0) AS deferrals,
                            s.prorated_annual_compensation AS comp,
                            CASE WHEN COALESCE(h.comp, s.current_compensation) > ?
                                 THEN TRUE ELSE FALSE END AS is_hce
                        FROM fct_workforce_snapshot s
                        LEFT JOIN prior_hce h ON s.employee_id = h.employee_id
                        WHERE s.simulation_year = ?
                          AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
                          AND s.prorated_annual_compensation > 0
                    )
                    SELECT deferrals / comp AS adp
                    FROM prior_data
                    WHERE is_hce = FALSE
                    """
                    # For prior year NHCE baseline, use year-2 for HCE determination of year-1
                    prior_hce_year = year - 2 if conn.execute(
                        "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                        [year - 2],
                    ).fetchone()[0] > 0 else year - 1

                    prior_nhce_rows = conn.execute(
                        prior_nhce_query, [prior_hce_year, hce_threshold, year - 1]
                    ).fetchall()

                    if prior_nhce_rows:
                        prior_year_nhce_adp = sum(r[0] for r in prior_nhce_rows) / len(prior_nhce_rows)
                    else:
                        actual_testing_method = "current"
                else:
                    actual_testing_method = "current"

            # Main ADP query with HCE determination
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
                    COALESCE(s.prorated_annual_contributions, 0) AS deferrals,
                    s.prorated_annual_compensation,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                WHERE s.simulation_year = ?
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
            ),
            per_employee AS (
                SELECT *,
                    CASE WHEN prorated_annual_compensation > 0
                         THEN deferrals / prorated_annual_compensation
                         ELSE 0 END AS individual_adp
                FROM current_year
            )
            SELECT
                employee_id,
                is_hce,
                deferrals,
                prorated_annual_compensation,
                individual_adp,
                prior_year_comp
            FROM per_employee
            ORDER BY is_hce DESC, individual_adp DESC
            """

            prior_year_param = year - 1 if prior_year_exists else year
            rows = conn.execute(query, [prior_year_param, hce_threshold, year]).fetchall()
            conn.close()

            if not rows:
                return ADPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="No eligible employees found for ADP test",
                    testing_method=actual_testing_method,
                )

            # Separate HCE/NHCE and compute ADPs
            hce_adps: List[float] = []
            nhce_adps: List[float] = []
            hce_compensations: List[float] = []
            employees: List[ADPEmployeeDetail] = []
            excluded_count = 0

            for row in rows:
                emp_id, is_hce, deferrals, comp, adp, prior_comp = row

                if comp is None or comp <= 0:
                    excluded_count += 1
                    continue

                if is_hce:
                    hce_adps.append(adp)
                    hce_compensations.append(float(comp))
                else:
                    nhce_adps.append(adp)

                if include_employees:
                    employees.append(ADPEmployeeDetail(
                        employee_id=str(emp_id),
                        is_hce=bool(is_hce),
                        employee_deferrals=float(deferrals),
                        plan_compensation=float(comp),
                        individual_adp=float(adp),
                        prior_year_compensation=float(prior_comp) if prior_comp is not None else None,
                    ))

            # Edge case: no NHCE
            if not nhce_adps:
                return ADPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="Insufficient NHCE population",
                    hce_count=len(hce_adps),
                    nhce_count=0,
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    testing_method=actual_testing_method,
                    employees=employees if include_employees else None,
                )

            # Edge case: no HCE -> auto-pass
            if not hce_adps:
                nhce_avg = sum(nhce_adps) / len(nhce_adps)
                return ADPScenarioResult(
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No HCE employees in population",
                    hce_count=0,
                    nhce_count=len(nhce_adps),
                    excluded_count=excluded_count,
                    hce_average_adp=0.0,
                    nhce_average_adp=nhce_avg,
                    hce_threshold_used=hce_threshold,
                    testing_method=actual_testing_method,
                    employees=employees if include_employees else None,
                )

            # Compute pass/fail
            nhce_baseline = prior_year_nhce_adp if actual_testing_method == "prior" and prior_year_nhce_adp is not None else None
            test_message = None
            if testing_method == "prior" and actual_testing_method == "current":
                test_message = "Prior year data not available — fell back to current year testing method"

            return self._compute_adp_result(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                year=year,
                hce_adps=hce_adps,
                nhce_adps=nhce_adps,
                hce_compensations=hce_compensations,
                hce_threshold=hce_threshold,
                excluded_count=excluded_count,
                testing_method=actual_testing_method,
                nhce_baseline_adp=nhce_baseline,
                test_message=test_message,
                employees=employees if include_employees else None,
            )

        except Exception as e:
            logger.error(f"Failed to run ADP test: {e}")
            return ADPScenarioResult(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=str(e),
                testing_method=testing_method,
            )

    def _compute_adp_result(
        self,
        scenario_id: str,
        scenario_name: str,
        year: int,
        hce_adps: List[float],
        nhce_adps: List[float],
        hce_compensations: List[float],
        hce_threshold: int,
        excluded_count: int,
        testing_method: str,
        nhce_baseline_adp: Optional[float],
        test_message: Optional[str],
        employees: Optional[List[ADPEmployeeDetail]],
    ) -> ADPScenarioResult:
        """Compute IRS ADP test pass/fail using basic and alternative tests."""
        hce_avg = sum(hce_adps) / len(hce_adps)
        nhce_avg = sum(nhce_adps) / len(nhce_adps)

        # Use prior year NHCE baseline if provided
        baseline_nhce = nhce_baseline_adp if nhce_baseline_adp is not None else nhce_avg

        # Basic test: NHCE avg x 1.25
        basic_threshold = baseline_nhce * 1.25

        # Alternative test: lesser of (NHCE avg x 2.0) and (NHCE avg + 0.02)
        alt_threshold = min(baseline_nhce * 2.0, baseline_nhce + 0.02)

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

        # Compute excess HCE amount when failing
        excess_hce_amount = None
        if test_result == "fail":
            total_hce_comp = sum(hce_compensations)
            excess_hce_amount = (hce_avg - applied_threshold) * total_hce_comp

        return ADPScenarioResult(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            simulation_year=year,
            test_result=test_result,
            test_message=test_message,
            hce_count=len(hce_adps),
            nhce_count=len(nhce_adps),
            excluded_count=excluded_count,
            hce_average_adp=hce_avg,
            nhce_average_adp=nhce_avg,
            basic_test_threshold=basic_threshold,
            alternative_test_threshold=alt_threshold,
            applied_test=applied_test,
            applied_threshold=applied_threshold,
            margin=margin,
            excess_hce_amount=excess_hce_amount,
            testing_method=testing_method,
            hce_threshold_used=hce_threshold,
            employees=employees,
        )
