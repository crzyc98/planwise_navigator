"""NDT (Non-Discrimination Testing) service for ACP, ADP, 401(a)(4), and 415 tests."""

from dataclasses import dataclass, field
import logging
import statistics
from typing import List, Optional

import yaml
from pydantic import Field, model_validator
from .ndt_selection import available_ndt_designs, select_ndt_design
from .ndt_input_validation import validate_ndt_inputs, validate_ndt_population
from .ndt_qnec import (
    ADPQNECEstimate,
    ADPQNECContext,
    NHCEQNECInput,
    estimate_uniform_qnec,
)
from .compliance_metrics import (
    annual_additions,
    base_deferrals,
    limit_status,
    applicable_deferral_limit,
)
from ..models.base import APIModel

from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)


def _effective_core_family(config: object, design_id: str | None) -> str | None:
    """Use selected-design family, then the established global UI precedence."""
    if not isinstance(config, dict):
        return None
    parameters = config.get("plan_design_parameters")
    if design_id is not None and isinstance(parameters, dict):
        design = parameters.get(design_id)
        core = design.get("employer_core") if isinstance(design, dict) else None
        family = core.get("family") if isinstance(core, dict) else None
        if isinstance(family, str) and family:
            return family
    dc_plan = config.get("dc_plan")
    dc_status = dc_plan.get("core_status") if isinstance(dc_plan, dict) else None
    if isinstance(dc_status, str) and dc_status:
        return dc_status
    core = config.get("employer_core_contribution")
    status = core.get("status") if isinstance(core, dict) else None
    return status if isinstance(status, str) else None


def _adp_thresholds(nhce_average: float) -> tuple[float, float, str, float]:
    basic = nhce_average * 1.25
    alternative = min(nhce_average * 2, nhce_average + 0.02)
    test = "basic" if basic >= alternative else "alternative"
    return basic, alternative, test, max(basic, alternative)


def _qnec_for_failure(
    test_result: str,
    testing_method: str,
    hce_adps: List[float],
    context: ADPQNECContext,
) -> Optional[ADPQNECEstimate]:
    if test_result != "fail":
        return None
    if testing_method == "prior":
        return ADPQNECEstimate(
            status="unsupported",
            reason="Prior-year testing is not supported by the QNEC estimate",
        )
    return estimate_uniform_qnec(hce_adps, context.nhce, context.annual_additions_limit)


@dataclass
class _ADPPopulation:
    hce_adps: List[float] = field(default_factory=list)
    nhce_adps: List[float] = field(default_factory=list)
    hce_compensations: List[float] = field(default_factory=list)
    nhce: List[NHCEQNECInput] = field(default_factory=list)
    employees: List["ADPEmployeeDetail"] = field(default_factory=list)
    excluded_count: int = 0


def _collect_adp_population(
    rows: List[tuple[str, bool, float, Optional[float], float, Optional[float], float]],
    include_employees: bool,
) -> _ADPPopulation:
    population = _ADPPopulation()
    for emp_id, is_hce, deferrals, comp, adp, prior_comp, additions in rows:
        if comp is None or comp <= 0:
            population.excluded_count += 1
            continue
        if is_hce:
            population.hce_adps.append(adp)
            population.hce_compensations.append(float(comp))
        else:
            population.nhce_adps.append(adp)
            population.nhce.append(
                NHCEQNECInput(float(comp), float(adp), float(additions))
            )
        if include_employees:
            population.employees.append(
                ADPEmployeeDetail(
                    employee_id=str(emp_id),
                    is_hce=bool(is_hce),
                    employee_deferrals=float(deferrals),
                    plan_compensation=float(comp),
                    individual_adp=float(adp),
                    prior_year_compensation=(
                        float(prior_comp) if prior_comp is not None else None
                    ),
                )
            )
    return population


# ==============================================================================
# Pydantic Response Models
# ==============================================================================


class ACPEmployeeDetail(APIModel):
    employee_id: str
    is_hce: bool
    is_enrolled: bool
    employer_match_amount: float
    eligible_compensation: float
    individual_acp: float
    prior_year_compensation: Optional[float] = None


class ACPScenarioResult(APIModel):
    plan_design_id: str | None = Field(
        default=None,
        description="Explicitly requested design; null retains legacy unselected behavior",
    )

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


class ACPTestResponse(APIModel):
    test_type: str = "acp"
    year: int
    results: List[ACPScenarioResult]


class AvailableYearsResponse(APIModel):
    plan_design_ids: List[str] = Field(
        default_factory=list,
        description="Candidate design IDs in the selected archive; each test validates its own population",
    )
    years: List[int]
    default_year: Optional[int] = None


# ==============================================================================
# 401(a)(4) General Test Response Models
# ==============================================================================


class Section401a4EmployeeDetail(APIModel):
    employee_id: str
    is_hce: bool
    employer_nec_amount: float = 0.0
    employer_match_amount: float = 0.0
    total_employer_amount: float = 0.0
    plan_compensation: float = 0.0
    contribution_rate: float = 0.0
    years_of_service: float = 0.0


class Section401a4ScenarioResult(APIModel):
    plan_design_id: str | None = Field(
        default=None,
        description="Explicitly requested design; null retains legacy unselected behavior",
    )

    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str = Field(
        description="Statutory determination: unavailable or execution error; heuristics do not establish qualification."
    )
    heuristic_result: Optional[str] = Field(
        default=None,
        description="Legacy average/median rate comparison only: pass or fail. Not a statutory test.",
    )
    test_message: Optional[str] = None
    applied_test: str = Field(
        default="ratio",
        description="Legacy heuristic selector: ratio means average rates; general means median rates. Neither is a statutory test.",
    )
    hce_count: int = 0
    nhce_count: int = 0
    excluded_count: int = 0
    hce_average_rate: float = 0.0
    nhce_average_rate: float = 0.0
    hce_median_rate: float = 0.0
    nhce_median_rate: float = 0.0
    ratio: float = Field(
        default=0.0,
        description="Legacy NHCE/HCE average-rate ratio; meaningful only when heuristic_result is non-null.",
    )
    ratio_test_threshold: float = Field(
        default=0.70,
        description="Legacy heuristic threshold, not the statutory rate-group coverage threshold.",
    )
    margin: float = Field(
        default=0.0,
        description="Legacy selected average or median ratio minus 0.70; meaningful only when heuristic_result is non-null.",
    )
    include_match: bool = False
    service_risk_flag: bool = False
    service_risk_detail: Optional[str] = None
    hce_threshold_used: int = 0
    employees: Optional[List[Section401a4EmployeeDetail]] = None

    @model_validator(mode="after")
    def distinguish_heuristic_from_determination(self) -> "Section401a4ScenarioResult":
        """Prevent every successful calculation path from claiming qualification."""
        if self.test_result in {"pass", "fail"}:
            self.heuristic_result = self.test_result
            self.test_result = "unavailable"
        if self.test_result == "unavailable":
            explanation = (
                "Statutory 401(a)(4) determination unavailable: rate-group coverage "
                "and required plan facts have not been evaluated. Average and median "
                "rate comparisons are descriptive heuristics for the selected "
                "contributing population only."
            )
            if not self.test_message or explanation not in self.test_message:
                self.test_message = explanation + (
                    " " + self.test_message if self.test_message else ""
                )
        return self


class Section401a4TestResponse(APIModel):
    test_type: str = "401a4"
    year: int
    results: List[Section401a4ScenarioResult]


# ==============================================================================
# 415 Annual Additions Limit Test Response Models
# ==============================================================================


class Section415EmployeeDetail(APIModel):
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


class Section415ScenarioResult(APIModel):
    plan_design_id: str | None = Field(
        default=None,
        description="Explicitly requested design; null retains legacy unselected behavior",
    )

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


class Section415TestResponse(APIModel):
    test_type: str = "415"
    year: int
    results: List[Section415ScenarioResult]


# ==============================================================================
# ADP (Actual Deferral Percentage) Test Response Models
# ==============================================================================


class ADPEmployeeDetail(APIModel):
    employee_id: str
    is_hce: bool
    employee_deferrals: float
    plan_compensation: float
    individual_adp: float
    prior_year_compensation: Optional[float] = None


class ADPScenarioResult(APIModel):
    plan_design_id: str | None = Field(
        default=None,
        description="Explicitly requested design; null retains legacy unselected behavior",
    )

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
    excess_hce_amount: Optional[float] = Field(
        default=None,
        description="Aggregate modeled estimate: (HCE average - threshold) x total HCE compensation; not a participant-level refund calculation",
    )
    qnec_estimate: Optional[ADPQNECEstimate] = None
    testing_method: str = "current"  # "current" or "prior"
    safe_harbor: bool = False
    hce_threshold_used: int = 0
    employees: Optional[List[ADPEmployeeDetail]] = None


class ADPTestResponse(APIModel):
    test_type: str = "adp"
    year: int
    results: List[ADPScenarioResult]


# ==============================================================================
# NDT Service
# ==============================================================================


class NDTService:
    """Read-only NDT analytics using limits materialized during initialization."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def get_available_years(
        self, workspace_id: str, scenario_id: str, plan_design_id: str | None = None
    ) -> AvailableYearsResponse:
        """Get available simulation years for NDT testing."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return AvailableYearsResponse(years=[], default_year=None)

        designs: list[str] = []
        try:
            with duckdb.connect(str(resolved.path), read_only=True) as conn:
                if resolved.source in ("scenario", "run"):
                    designs = available_ndt_designs(conn)
                select_ndt_design(conn, resolved, plan_design_id)
                result = conn.execute(
                    "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year"
                ).fetchall()

            years = [row[0] for row in result]
            default_year = years[-1] if years else None
            return AvailableYearsResponse(
                years=years, default_year=default_year, plan_design_ids=designs
            )
        except Exception as e:
            logger.error(f"Failed to get available years: {e}")
            return AvailableYearsResponse(
                years=[], default_year=None, plan_design_ids=designs
            )

    def run_acp_test(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        year: int,
        include_employees: bool = False,
        plan_design_id: str | None = None,
    ) -> ACPScenarioResult:
        """Run the ACP non-discrimination test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return ACPScenarioResult(
                plan_design_id=plan_design_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        assert resolved.path is not None  # guaranteed by resolved.exists check above

        try:
            with duckdb.connect(str(resolved.path), read_only=True) as conn:
                select_ndt_design(conn, resolved, plan_design_id, year, lookback=1)
                validate_ndt_population(conn, year, 1)
                validate_ndt_inputs(conn, year, "acp")
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
                        return ACPScenarioResult(
                            plan_design_id=plan_design_id,
                            scenario_id=scenario_id,
                            scenario_name=scenario_name,
                            simulation_year=year,
                            test_result="error",
                            test_message=f"HCE compensation threshold not found in config_irs_limits for year {year - 1} or {year}.",
                        )

                hce_threshold = int(hce_threshold_row[0])

                # Check if prior year data exists
                prior_year_count_row = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year - 1],
                ).fetchone()
                prior_year_exists = (
                    prior_year_count_row is not None and prior_year_count_row[0] > 0
                )

                after_tax_expression = "0.0"
                after_tax_columns = (
                    "employee_after_tax_contributions",
                    "employee_after_tax_contribution",
                    "after_tax_contributions",
                    "after_tax_contribution",
                )
                for column_name in after_tax_columns:
                    has_column = conn.execute(
                        """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'main'
                      AND table_name = 'fct_workforce_snapshot'
                      AND column_name = ?
                    LIMIT 1
                    """,
                        [column_name],
                    ).fetchone()
                    if has_column:
                        after_tax_expression = f"COALESCE(s.{column_name}, 0)"
                        break

                # Main ACP query with HCE determination. prorated_annual_compensation
                # is the project's uncapped 414(s) testing compensation proxy; cap it
                # at query time for ACP. After-tax defaults explicitly to zero until
                # that contribution type is propagated to fct_workforce_snapshot.
                query = """
            WITH prior_year AS (
                SELECT employee_id, current_compensation AS prior_year_comp
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
            ),
            irs_limits AS (
                SELECT compensation_limit
                FROM config_irs_limits
                WHERE limit_year = ?
            ),
            current_year AS (
                SELECT
                    s.employee_id,
                    s.current_eligibility_status,
                    s.is_enrolled_flag,
                    COALESCE(s.employer_match_amount, 0) AS employer_match_amount,
                    {after_tax_expression} AS employee_after_tax_contributions,
                    CASE WHEN s.prorated_annual_compensation IS NULL
                         THEN NULL
                         ELSE LEAST(
                             s.prorated_annual_compensation,
                             il.compensation_limit
                         ) END AS testing_comp_414s_capped,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                CROSS JOIN irs_limits il
                WHERE s.simulation_year = ?
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
            ),
            per_employee AS (
                SELECT *,
                    CASE WHEN testing_comp_414s_capped > 0
                         THEN (employer_match_amount + employee_after_tax_contributions)
                              / testing_comp_414s_capped
                         ELSE 0 END AS individual_acp
                FROM current_year
            )
            SELECT
                employee_id,
                is_hce,
                is_enrolled_flag,
                employer_match_amount,
                testing_comp_414s_capped AS eligible_compensation,
                individual_acp,
                prior_year_comp
            FROM per_employee
            ORDER BY is_hce DESC, individual_acp DESC
            """.format(after_tax_expression=after_tax_expression)

                prior_year_param = year - 1 if prior_year_exists else year
                rows = conn.execute(
                    query, [prior_year_param, year, hce_threshold, year]
                ).fetchall()

            assumption = (
                "Legacy after-tax contribution column absent; ACP assumes zero after-tax contributions."
                if after_tax_expression == "0.0"
                else ""
            )
            if not rows:
                return ACPScenarioResult(
                    plan_design_id=plan_design_id,
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
            excluded_count = 0

            for row in rows:
                emp_id, is_hce, is_enrolled, match_amt, comp, acp, prior_comp = row
                if comp is None or comp <= 0:
                    excluded_count += 1
                    continue

                if is_hce:
                    hce_acps.append(acp)
                else:
                    nhce_acps.append(acp)
                if not is_enrolled:
                    eligible_not_enrolled += 1
                if include_employees:
                    employees.append(
                        ACPEmployeeDetail(
                            employee_id=str(emp_id),
                            is_hce=bool(is_hce),
                            is_enrolled=bool(is_enrolled),
                            employer_match_amount=float(match_amt),
                            eligible_compensation=float(comp),
                            individual_acp=float(acp),
                            prior_year_compensation=(
                                float(prior_comp) if prior_comp is not None else None
                            ),
                        )
                    )

            # Edge case: no NHCE employees
            if not nhce_acps:
                return ACPScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="Insufficient NHCE population. " + assumption,
                    hce_count=len(hce_acps),
                    nhce_count=0,
                    hce_threshold_used=hce_threshold,
                    employees=employees if include_employees else None,
                )

            # Edge case: no HCE employees -> auto-pass
            if not hce_acps:
                nhce_avg = sum(nhce_acps) / len(nhce_acps)
                return ACPScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No HCE employees in population. " + assumption,
                    hce_count=0,
                    nhce_count=len(nhce_acps),
                    hce_average_acp=0.0,
                    nhce_average_acp=nhce_avg,
                    hce_threshold_used=hce_threshold,
                    eligible_not_enrolled_count=eligible_not_enrolled,
                    employees=employees if include_employees else None,
                )

            # Compute pass/fail
            result = self._compute_test_result(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                year=year,
                hce_acps=hce_acps,
                nhce_acps=nhce_acps,
                hce_threshold=hce_threshold,
                eligible_not_enrolled=eligible_not_enrolled,
                excluded_count=excluded_count,
                employees=employees if include_employees else None,
            )

            result.test_message = assumption or None
            result.plan_design_id = plan_design_id
            return result

        except Exception as e:
            logger.error(f"Failed to run ACP test: {e}")
            return ACPScenarioResult(
                plan_design_id=plan_design_id,
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
        plan_design_id: str | None = None,
    ) -> Section401a4ScenarioResult:
        """Run the 401(a)(4) general nondiscrimination test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return Section401a4ScenarioResult(
                plan_design_id=plan_design_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        assert resolved.path is not None  # guaranteed by resolved.exists check above

        try:
            with duckdb.connect(str(resolved.path), read_only=True) as conn:
                select_ndt_design(conn, resolved, plan_design_id, year, lookback=1)
                validate_ndt_population(conn, year, 1)
                validate_ndt_inputs(conn, year, "401a4")
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
                        return Section401a4ScenarioResult(
                            plan_design_id=plan_design_id,
                            scenario_id=scenario_id,
                            scenario_name=scenario_name,
                            simulation_year=year,
                            test_result="error",
                            test_message=f"HCE compensation threshold not found for year {year - 1} or {year}.",
                        )

                hce_threshold = int(hce_threshold_row[0])

                # Check prior year data
                prior_year_exists_row = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year - 1],
                ).fetchone()
                assert prior_year_exists_row is not None
                prior_year_exists = prior_year_exists_row[0] > 0

                prior_year_param = year - 1 if prior_year_exists else year

                # Main query for 401(a)(4) test. prorated_annual_compensation is the
                # uncapped 414(s) testing compensation proxy; cap it at query time.
                query = """
            WITH prior_year AS (
                SELECT employee_id, current_compensation AS prior_year_comp
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
            ),
            irs_limits AS (
                SELECT compensation_limit
                FROM config_irs_limits
                WHERE limit_year = ?
            ),
            current_year AS (
                SELECT
                    s.employee_id,
                    s.current_eligibility_status,
                    CASE WHEN s.prorated_annual_compensation IS NULL
                         THEN NULL
                         ELSE LEAST(
                             s.prorated_annual_compensation,
                             il.compensation_limit
                         ) END AS testing_comp_414s_capped,
                    COALESCE(s.employer_core_amount, 0) AS employer_core_amount,
                    COALESCE(s.employer_match_amount, 0) AS employer_match_amount,
                    s.current_tenure,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                CROSS JOIN irs_limits il
                WHERE s.simulation_year = ?
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
            )
            SELECT
                employee_id,
                is_hce,
                employer_core_amount,
                employer_match_amount,
                testing_comp_414s_capped,
                current_tenure
            FROM current_year
            WHERE (employer_core_amount > 0 OR employer_match_amount > 0)
            ORDER BY is_hce DESC
            """

                rows = conn.execute(
                    query, [prior_year_param, year, hce_threshold, year]
                ).fetchall()

            if not rows:
                return Section401a4ScenarioResult(
                    plan_design_id=plan_design_id,
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
                    employees.append(
                        Section401a4EmployeeDetail(
                            employee_id=str(emp_id),
                            is_hce=bool(is_hce),
                            employer_nec_amount=float(core_amt),
                            employer_match_amount=(
                                float(match_amt) if include_match else 0.0
                            ),
                            total_employer_amount=float(total_employer),
                            plan_compensation=float(plan_comp),
                            contribution_rate=float(rate),
                            years_of_service=float(tenure or 0),
                        )
                    )

            # Edge case: no NHCE employees
            if not nhce_rates:
                result = Section401a4ScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="unavailable",
                    test_message="No NHCE employees in population; rate comparison unavailable",
                    hce_count=len(hce_rates),
                    nhce_count=0,
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )
                self._detect_service_risk(
                    result,
                    workspace_id,
                    scenario_id,
                    hce_tenures,
                    nhce_tenures,
                    resolved,
                )
                return result

            # Edge case: no HCE employees -> auto-pass
            if not hce_rates:
                result = Section401a4ScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="unavailable",
                    test_message="No HCE employees in population; rate comparison unavailable",
                    hce_count=0,
                    nhce_count=len(nhce_rates),
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )
                self._detect_service_risk(
                    result,
                    workspace_id,
                    scenario_id,
                    hce_tenures,
                    nhce_tenures,
                    resolved,
                )
                return result

            # Edge case: no employer contributions at all
            if all(abs(r) < 1e-9 for r in hce_rates) and all(
                abs(r) < 1e-9 for r in nhce_rates
            ):
                result = Section401a4ScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="unavailable",
                    test_message="No employer contributions; rate comparison unavailable",
                    hce_count=len(hce_rates),
                    nhce_count=len(nhce_rates),
                    excluded_count=excluded_count,
                    hce_threshold_used=hce_threshold,
                    include_match=include_match,
                    employees=employees if include_employees else None,
                )
                self._detect_service_risk(
                    result,
                    workspace_id,
                    scenario_id,
                    hce_tenures,
                    nhce_tenures,
                    resolved,
                )
                return result

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

            result.plan_design_id = plan_design_id
            # Service-based risk detection (T008)
            self._detect_service_risk(
                result, workspace_id, scenario_id, hce_tenures, nhce_tenures, resolved
            )

            result.plan_design_id = plan_design_id
            return result

        except Exception as e:
            logger.error(f"Failed to run 401(a)(4) test: {e}")
            return Section401a4ScenarioResult(
                plan_design_id=plan_design_id,
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
        resolved: ResolvedDatabasePath,
    ) -> None:
        """Detect service-based NEC tenure skew risk (mutates result in-place)."""
        try:
            if resolved.config_path is not None:
                config = yaml.safe_load(
                    resolved.config_path.read_text(encoding="utf-8")
                )
            else:
                config = self.storage.get_merged_config(workspace_id, scenario_id)
            ec_status = _effective_core_family(config, result.plan_design_id)

            if ec_status == "age_banded":
                result.service_risk_flag = True
                result.service_risk_detail = (
                    "Age-banded employer core contributions require further "
                    "nondiscrimination review."
                )
                return

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
        plan_design_id: str | None = None,
    ) -> Section415ScenarioResult:
        """Run the Section 415 annual additions limit test for a single scenario and year."""
        import duckdb

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return Section415ScenarioResult(
                plan_design_id=plan_design_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
            )

        assert resolved.path is not None  # guaranteed by resolved.exists check above
        try:
            with duckdb.connect(str(resolved.path), read_only=True) as conn:
                select_ndt_design(conn, resolved, plan_design_id, year, lookback=0)
                validate_ndt_population(conn, year, 0)
                validate_ndt_inputs(conn, year, "415")
                # Get IRS limits for the test year
                limits_row = conn.execute(
                    "SELECT annual_additions_limit, base_limit, catch_up_age_threshold, catch_up_limit, super_catch_up_limit, super_catch_up_age_min, super_catch_up_age_max FROM config_irs_limits WHERE limit_year = ?",
                    [year],
                ).fetchone()

                if not limits_row or any(value is None for value in limits_row):
                    return Section415ScenarioResult(
                        plan_design_id=plan_design_id,
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        simulation_year=year,
                        test_result="error",
                        test_message=f"IRS limits not found in config_irs_limits for year {year}",
                    )

                annual_additions_limit = int(limits_row[0])
                base_limit = int(limits_row[1])
                catch_up_age = int(limits_row[2])
                columns = {
                    row[0]
                    for row in conn.execute(
                        "DESCRIBE fct_workforce_snapshot"
                    ).fetchall()
                }
                age_expression = "current_age" if "current_age" in columns else "NULL"
                if "employee_birth_date" in columns:
                    age_expression = f"COALESCE({year} - YEAR(employee_birth_date), {age_expression})"
                if "source_year_end_age" in columns:
                    legacy_age = age_expression
                    age_expression = f"COALESCE(source_year_end_age, {legacy_age})"
                    if "contribution_source_version" in columns:
                        age_expression = f"CASE WHEN contribution_source_version IS NULL THEN {legacy_age} ELSE {age_expression} END"

                # Query eligible participants
                query = """
            SELECT
                employee_id,
                current_compensation,
                prorated_annual_compensation,
                COALESCE(prorated_annual_contributions, 0) AS contributions,
                COALESCE(employer_match_amount, 0) AS match_amount,
                COALESCE(employer_core_amount, 0) AS core_amount,
                {age_expression} AS age
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
              AND (current_eligibility_status = 'eligible' OR current_eligibility_status IS NULL)
            """

                rows = conn.execute(
                    query.format(age_expression=age_expression), [year]
                ).fetchall()

            # Process participants
            employees: List[Section415EmployeeDetail] = []
            breach_count = 0
            at_risk_count = 0
            passing_count = 0
            excluded_count = 0
            max_utilization = 0.0

            for row in rows:
                (
                    emp_id,
                    gross_comp,
                    prorated_comp,
                    contributions,
                    match_amt,
                    core_amt,
                    age,
                ) = row

                if gross_comp is None or gross_comp <= 0:
                    excluded_count += 1
                    continue

                # Only age-eligible catch-up within its dollar allowance is excluded.
                total_deferral_limit = applicable_deferral_limit(
                    age,
                    base_limit,
                    float(limits_row[3]),
                    float(limits_row[4]),
                    catch_up_age,
                    int(limits_row[5]),
                    int(limits_row[6]),
                )
                deferrals = base_deferrals(
                    float(contributions),
                    base_limit,
                    age,
                    catch_up_age,
                    total_deferral_limit,
                )

                # Total annual additions
                total_additions = annual_additions(
                    float(contributions),
                    float(match_amt),
                    float(core_amt),
                    base_limit,
                    age,
                    catch_up_age,
                    total_deferral_limit,
                )

                # Applicable 415 limit = lesser of IRS dollar limit or 100% of gross comp
                applicable_limit = min(float(annual_additions_limit), float(gross_comp))

                headroom = applicable_limit - total_additions
                utilization = (
                    total_additions / applicable_limit if applicable_limit > 0 else 0.0
                )
                max_utilization = max(max_utilization, utilization)

                # Classify
                status = limit_status(
                    total_additions, applicable_limit, warning_threshold
                )
                if status == "over_limit":
                    emp_status = "breach"
                    breach_count += 1
                elif status in ("near_limit", "at_limit"):
                    emp_status = "at_risk"
                    at_risk_count += 1
                else:
                    emp_status = "pass"
                    passing_count += 1

                if include_employees:
                    employees.append(
                        Section415EmployeeDetail(
                            employee_id=str(emp_id),
                            status=emp_status,
                            employee_deferrals=deferrals,
                            employer_match=float(match_amt),
                            employer_nec=float(core_amt),
                            total_annual_additions=total_additions,
                            gross_compensation=float(gross_comp),
                            applicable_limit=applicable_limit,
                            headroom=headroom,
                            utilization_pct=utilization,
                        )
                    )

            total_participants = breach_count + at_risk_count + passing_count
            test_result = "fail" if breach_count > 0 else "pass"

            return Section415ScenarioResult(
                plan_design_id=plan_design_id,
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
                plan_design_id=plan_design_id,
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
        plan_design_id: str | None = None,
    ) -> ADPScenarioResult:
        """Run the ADP non-discrimination test for a single scenario and year."""
        import duckdb

        # Safe harbor short-circuit
        if safe_harbor and plan_design_id is None:
            return ADPScenarioResult(
                plan_design_id=plan_design_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="exempt",
                test_message="Config-only safe harbor assumption — ADP exempt; no population determination",
                safe_harbor=True,
                testing_method=testing_method,
            )

        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return ADPScenarioResult(
                plan_design_id=plan_design_id,
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                simulation_year=year,
                test_result="error",
                test_message=f"Database not found for scenario {scenario_id}",
                testing_method=testing_method,
            )

        assert resolved.path is not None  # guaranteed by resolved.exists check above
        try:
            with duckdb.connect(str(resolved.path), read_only=True) as conn:
                select_ndt_design(
                    conn,
                    resolved,
                    plan_design_id,
                    year,
                    lookback=2 if testing_method == "prior" else 1,
                )
                validate_ndt_population(
                    conn, year, 2 if testing_method == "prior" else 1
                )
                if safe_harbor:
                    raise ValueError(
                        "Design-specific safe harbor applicability is not established"
                    )
                validate_ndt_inputs(conn, year, "adp")
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
                        return ADPScenarioResult(
                            plan_design_id=plan_design_id,
                            scenario_id=scenario_id,
                            scenario_name=scenario_name,
                            simulation_year=year,
                            test_result="error",
                            test_message=f"HCE compensation threshold not found in config_irs_limits for year {year - 1} or {year}.",
                            testing_method=testing_method,
                        )

                hce_threshold = int(hce_threshold_row[0])

                # Check if prior year data exists
                prior_year_count_row = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year - 1],
                ).fetchone()
                prior_year_exists = (
                    prior_year_count_row is not None and prior_year_count_row[0] > 0
                )

                # Prior year testing method: get NHCE ADP from prior year
                prior_year_nhce_adp = None
                actual_testing_method = testing_method
                if testing_method == "prior":
                    if prior_year_exists:
                        validate_ndt_inputs(conn, year - 1, "adp", prior_baseline=True)
                        prior_nhce_query = """
                    WITH prior_hce AS (
                        SELECT employee_id, current_compensation AS comp
                        FROM fct_workforce_snapshot
                        WHERE simulation_year = ?
                    ),
                    irs_limits AS (
                        SELECT compensation_limit, base_limit
                        FROM config_irs_limits
                        WHERE limit_year = ?
                    ),
                    prior_data AS (
                        SELECT
                            s.employee_id,
                            LEAST(
                                COALESCE(s.prorated_annual_contributions, 0),
                                il.base_limit
                            ) AS deferrals,
                            CASE WHEN s.prorated_annual_compensation IS NULL
                                 THEN NULL
                                 ELSE LEAST(
                                     s.prorated_annual_compensation,
                                     il.compensation_limit
                                 ) END AS comp,
                            CASE WHEN COALESCE(h.comp, s.current_compensation) > ?
                                 THEN TRUE ELSE FALSE END AS is_hce
                        FROM fct_workforce_snapshot s
                        LEFT JOIN prior_hce h ON s.employee_id = h.employee_id
                        CROSS JOIN irs_limits il
                        WHERE s.simulation_year = ?
                          AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
                    )
                    SELECT deferrals / comp AS adp
                    FROM prior_data
                    WHERE is_hce = FALSE
                      AND comp > 0
                    """
                        # For prior year NHCE baseline, use year-2 for HCE determination of year-1
                        year_minus_2_count_row = conn.execute(
                            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                            [year - 2],
                        ).fetchone()
                        year_minus_2_exists = (
                            year_minus_2_count_row is not None
                            and year_minus_2_count_row[0] > 0
                        )
                        prior_hce_year = year - 2 if year_minus_2_exists else year - 1

                        prior_nhce_rows = conn.execute(
                            prior_nhce_query,
                            [prior_hce_year, year - 1, hce_threshold, year - 1],
                        ).fetchall()

                        if prior_nhce_rows:
                            prior_year_nhce_adp = sum(
                                r[0] for r in prior_nhce_rows
                            ) / len(prior_nhce_rows)
                        else:
                            actual_testing_method = "current"
                    else:
                        actual_testing_method = "current"

                if (
                    plan_design_id is not None
                    and testing_method == "prior"
                    and prior_year_nhce_adp is None
                ):
                    raise ValueError(
                        "NDT selected design has no usable prior-year NHCE baseline"
                    )

                # Main ADP query with HCE determination. ADP uses capped 414(s)
                # testing compensation as denominator and 402(g) base-limit-capped
                # deferrals as numerator, excluding catch-up.
                query = """
            WITH prior_year AS (
                SELECT employee_id, current_compensation AS prior_year_comp
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
            ),
            irs_limits AS (
                SELECT compensation_limit, base_limit
                FROM config_irs_limits
                WHERE limit_year = ?
            ),
            current_year AS (
                SELECT
                    s.employee_id,
                    s.current_eligibility_status,
                    COALESCE(s.employer_match_amount, 0) AS match_amount,
                    COALESCE(s.employer_core_amount, 0) AS core_amount,
                    LEAST(
                        COALESCE(s.prorated_annual_contributions, 0),
                        il.base_limit
                    ) AS adp_base_deferrals,
                    CASE WHEN s.prorated_annual_compensation IS NULL
                         THEN NULL
                         ELSE LEAST(
                             s.prorated_annual_compensation,
                             il.compensation_limit
                         ) END AS testing_comp_414s_capped,
                    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
                    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > ?
                         THEN TRUE ELSE FALSE END AS is_hce
                FROM fct_workforce_snapshot s
                LEFT JOIN prior_year p ON s.employee_id = p.employee_id
                CROSS JOIN irs_limits il
                WHERE s.simulation_year = ?
                  AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
            ),
            per_employee AS (
                SELECT *,
                    CASE WHEN testing_comp_414s_capped > 0
                         THEN adp_base_deferrals / testing_comp_414s_capped
                         ELSE 0 END AS individual_adp
                FROM current_year
            )
            SELECT
                employee_id,
                is_hce,
                adp_base_deferrals,
                testing_comp_414s_capped,
                individual_adp,
                prior_year_comp,
                -- 415 annual additions exclude catch-up: deferrals above the 402(g) base limit
                adp_base_deferrals + match_amount + core_amount AS annual_additions
            FROM per_employee
            ORDER BY is_hce DESC, individual_adp DESC
            """

                limit_row = conn.execute(
                    "SELECT annual_additions_limit FROM config_irs_limits WHERE limit_year = ?",
                    [year],
                ).fetchone()
                additions_limit = (
                    float(limit_row[0])
                    if limit_row and limit_row[0] is not None
                    else None
                )
                prior_year_param = year - 1 if prior_year_exists else year
                rows = conn.execute(
                    query, [prior_year_param, year, hce_threshold, year]
                ).fetchall()
                missing_prior_count = conn.execute(
                    """SELECT COUNT(*) FROM fct_workforce_snapshot s
                    LEFT JOIN fct_workforce_snapshot p
                      ON s.employee_id = p.employee_id AND p.simulation_year = ?
                    WHERE s.simulation_year = ?
                      AND (s.current_eligibility_status = 'eligible'
                           OR s.current_eligibility_status IS NULL)
                      AND s.prorated_annual_compensation > 0
                      AND p.current_compensation IS NULL""",
                    [year - 1, year],
                ).fetchone()[0]

            evidence_message = (
                f"HCE classification uses current compensation for {missing_prior_count} "
                "employee(s) missing prior-year compensation; this is a modeled "
                "assumption, not observed prior-year pay."
                if missing_prior_count
                else ""
            )

            if not rows:
                return ADPScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="No eligible employees found for ADP test",
                    testing_method=actual_testing_method,
                )

            population = _collect_adp_population(rows, include_employees)
            hce_adps, nhce_adps = population.hce_adps, population.nhce_adps
            employees, excluded_count = population.employees, population.excluded_count

            # Edge case: no NHCE
            if not nhce_adps:
                return ADPScenarioResult(
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="error",
                    test_message="Insufficient NHCE population. " + evidence_message,
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
                    plan_design_id=plan_design_id,
                    scenario_id=scenario_id,
                    scenario_name=scenario_name,
                    simulation_year=year,
                    test_result="pass",
                    test_message="No HCE employees in population. " + evidence_message,
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
            nhce_baseline = (
                prior_year_nhce_adp
                if actual_testing_method == "prior" and prior_year_nhce_adp is not None
                else None
            )
            test_message = evidence_message or None
            if testing_method == "prior" and actual_testing_method == "current":
                test_message = (
                    "Prior year data not available — fell back to current year testing method. "
                    + evidence_message
                )

            result = self._compute_adp_result(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                year=year,
                hce_adps=hce_adps,
                nhce_adps=nhce_adps,
                qnec_context=ADPQNECContext(
                    population.hce_compensations, population.nhce, additions_limit
                ),
                hce_threshold=hce_threshold,
                excluded_count=excluded_count,
                testing_method=actual_testing_method,
                nhce_baseline_adp=nhce_baseline,
                test_message=test_message,
                employees=employees if include_employees else None,
            )

            result.plan_design_id = plan_design_id
            return result

        except Exception as e:
            logger.error(f"Failed to run ADP test: {e}")
            return ADPScenarioResult(
                plan_design_id=plan_design_id,
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
        qnec_context: ADPQNECContext,
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

        baseline_nhce = nhce_baseline_adp if nhce_baseline_adp is not None else nhce_avg
        basic_threshold, alt_threshold, applied_test, applied_threshold = (
            _adp_thresholds(baseline_nhce)
        )
        test_result = "pass" if hce_avg <= applied_threshold else "fail"
        margin = applied_threshold - hce_avg
        excess_hce_amount = None
        if test_result == "fail":
            total_hce_comp = sum(qnec_context.hce_compensations)
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
            qnec_estimate=_qnec_for_failure(
                test_result, testing_method, hce_adps, qnec_context
            ),
            testing_method=testing_method,
            hce_threshold_used=hce_threshold,
            employees=employees,
        )
