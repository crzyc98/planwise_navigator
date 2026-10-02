"""Compliance projections over immutable selected results, without database writes."""

import csv
import hashlib
import json

import duckdb

from ..models.compliance import (
    CatchUpRollup,
    ComplianceEmployee,
    ComplianceEmployeePage,
    ComplianceLimits,
    ComplianceNDTResult,
    ComplianceSummary,
    LimitMeasure,
    LimitRollup,
    MetricName,
)
from ..storage.workspace_storage import WorkspaceStorage
from .compliance_metrics import (
    LimitStatus,
    annual_additions,
    cents,
    limit_status,
    applicable_deferral_limit,
)
from .database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    create_api_database_path_resolver,
)
from .ndt_service import (
    NDTService,
    ADPScenarioResult,
    ACPScenarioResult,
    Section415ScenarioResult,
)


class ComplianceEvidenceChangedError(ValueError):
    """Selected reporting evidence changed; the client must refresh its summary."""


class _PinnedResolver(DatabasePathResolver):
    def __init__(self, resolved: ResolvedDatabasePath) -> None:
        self.resolved = resolved

    def resolve(
        self, workspace_id: str, scenario_id: str, *, verify_database: bool = True
    ) -> ResolvedDatabasePath:
        return self.resolved


def _evidence(resolved: ResolvedDatabasePath, year: int, threshold: float) -> str:
    entries = [resolved.run_id, year, threshold]
    for path in (resolved.path, resolved.config_path):
        if path is not None:
            stat = path.stat()
            entries.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def _measure(
    amount: float | None, limit: float | None, threshold: float
) -> LimitMeasure:
    status = limit_status(amount, limit, threshold)
    if amount is None or limit is None or status == "unavailable":
        return LimitMeasure(amount=amount, limit=limit)
    difference = float(cents(limit) - cents(amount))
    return LimitMeasure(
        amount=amount,
        limit=limit,
        headroom=difference,
        excess=max(0, -difference),
        utilization=amount / limit,
        status=status,
    )


def _rollup(employees: list[ComplianceEmployee], field: str) -> LimitRollup:
    counts = LimitRollup()
    total_excess = cents(0)
    for employee in employees:
        measure = getattr(employee, field)
        setattr(counts, measure.status, getattr(counts, measure.status) + 1)
        total_excess += cents(measure.excess or 0)
    counts.excess = float(total_excess)
    return counts


def _catch_up(employees: list[ComplianceEmployee], group: str) -> CatchUpRollup:
    eligible = [e for e in employees if e.catch_up_group == group]
    available = [
        (e.catch_up_capacity, e.modeled_catch_up_used)
        for e in eligible
        if e.catch_up_capacity is not None and e.modeled_catch_up_used is not None
    ]
    capacity = sum((cents(capacity) for capacity, _ in available), cents(0))
    used = sum((cents(used) for _, used in available), cents(0))
    return CatchUpRollup(
        eligible_count=len(eligible),
        available_count=len(available),
        utilizing_count=sum(used > 0 for _, used in available),
        capacity=float(capacity),
        used=float(used),
        remaining_capacity=float(capacity - used),
        utilization=float(used / capacity) if capacity > 0 else None,
    )


def _limits(conn: duckdb.DuckDBPyConnection, year: int) -> ComplianceLimits | None:
    if not conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'config_irs_limits'"
    ).fetchone():
        return None
    columns = {row[0] for row in conn.execute("DESCRIBE config_irs_limits").fetchall()}
    names = [
        "base_limit",
        "catch_up_limit",
        "super_catch_up_limit",
        "compensation_limit",
        "annual_additions_limit",
        "catch_up_age_threshold",
        "super_catch_up_age_min",
        "super_catch_up_age_max",
    ]
    if not set(names).issubset(columns):
        return None
    estimated = "is_estimated" if "is_estimated" in columns else "NULL"
    row = conn.execute(
        f"SELECT {', '.join(names)}, {estimated} FROM config_irs_limits WHERE limit_year = ?",
        [year],
    ).fetchone()
    if row is None or any(value is None or value <= 0 for value in row[:-1]):
        return None
    values = dict(zip([*names, "is_estimated"], row))
    with (NDTService._SEEDS_DIR / "config_irs_limits.csv").open(newline="") as source:
        current = next(
            (r for r in csv.DictReader(source) if int(r["limit_year"]) == year), None
        )
    differs = current is not None and any(
        float(current[name]) != values[name] for name in names
    )
    return ComplianceLimits(year=year, **values, differs_from_current_seed=differs)


def _employee(
    row: dict, limits: ComplianceLimits | None, threshold: float
) -> ComplianceEmployee:
    age = row["current_age"]
    contributions = row["prorated_annual_contributions"]
    group, applicable = None, None
    if limits and age is not None:
        applicable = limits.base_limit
        if (
            limits.super_catch_up_age_min <= age <= limits.super_catch_up_age_max
            and limits.super_catch_up_limit > limits.catch_up_limit
        ):
            group, applicable = "super", limits.super_catch_up_limit
        elif age >= limits.catch_up_age_threshold:
            group, applicable = "ordinary", limits.catch_up_limit
    additions = _additions(row, limits)
    gross = row["current_compensation"]
    annual_limit = (
        min(limits.annual_additions_limit, gross)
        if limits and gross and gross > 0
        else None
    )
    result = ComplianceEmployee(
        employee_id=row["employee_id"],
        plan_design_id=row["plan_design_id"],
        age=age,
        deferrals=_measure(contributions, applicable, threshold),
        annual_additions=_measure(additions, annual_limit, threshold),
        compensation=_measure(
            row["prorated_annual_compensation"],
            limits.compensation_limit if limits else None,
            threshold,
        ),
        catch_up_group=group,
    )
    if group and limits and applicable is not None:
        _apply_catch_up(result, contributions, applicable, limits.base_limit)
    return result


def _apply_catch_up(
    employee: ComplianceEmployee,
    contributions: float | None,
    applicable: float,
    base_limit: float,
) -> None:
    employee.catch_up_capacity = applicable - base_limit
    if contributions is None or contributions < 0:
        return
    employee.modeled_catch_up_used = min(
        max(0, contributions - base_limit), employee.catch_up_capacity
    )
    employee.remaining_catch_up_capacity = (
        employee.catch_up_capacity - employee.modeled_catch_up_used
    )


def _ndt_coverage(
    results: list[ComplianceNDTResult],
    rows: list[dict],
    employees: list[ComplianceEmployee],
) -> list[ComplianceNDTResult]:
    missing = {
        "adp": any(
            r["prorated_annual_contributions"] is None
            or r["prorated_annual_compensation"] is None
            for r in rows
        ),
        "acp": any(
            r["employer_match_amount"] is None
            or r["prorated_annual_compensation"] is None
            for r in rows
        ),
        "415": any(e.annual_additions.status == "unavailable" for e in employees),
    }
    for result in results:
        if not employees or missing[result.test_type]:
            result.result, result.margin = "unavailable", None
            result.message = "No eligible population is available, or required reporting inputs are missing; no test result is asserted."
    return results


def _additions(row: dict, limits: ComplianceLimits | None) -> float | None:
    fields = [
        row[name]
        for name in (
            "prorated_annual_contributions",
            "employer_match_amount",
            "employer_core_amount",
        )
    ]
    if (
        not limits
        or row["current_age"] is None
        or any(v is None or v < 0 for v in fields)
    ):
        return None
    return annual_additions(
        fields[0],
        fields[1],
        fields[2],
        limits.base_limit,
        row["current_age"],
        limits.catch_up_age_threshold,
        applicable_deferral_limit(
            row["current_age"],
            limits.base_limit,
            limits.catch_up_limit,
            limits.super_catch_up_limit,
            limits.catch_up_age_threshold,
            limits.super_catch_up_age_min,
            limits.super_catch_up_age_max,
        ),
    )


class ComplianceService:
    def __init__(
        self, storage: WorkspaceStorage, db_resolver: DatabasePathResolver | None = None
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def _read(
        self, workspace_id: str, scenario_id: str, year: int, threshold: float
    ) -> tuple[ResolvedDatabasePath, str, ComplianceLimits | None, list[dict]]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            raise ValueError(
                "No successful result is available for compliance reporting"
            )
        evidence = _evidence(resolved, year, threshold)
        with duckdb.connect(str(resolved.path), read_only=True) as conn:
            columns = {
                r[0] for r in conn.execute("DESCRIBE fct_workforce_snapshot").fetchall()
            }
            optional = ["plan_design_id", "current_age"]
            fields = [
                "employee_id",
                "current_compensation",
                "prorated_annual_compensation",
                "prorated_annual_contributions",
                "employer_match_amount",
                "employer_core_amount",
            ]
            expressions = fields + [
                name if name in columns else f"NULL AS {name}" for name in optional
            ]
            rows = conn.execute(
                f"SELECT {', '.join(expressions)} FROM fct_workforce_snapshot WHERE simulation_year = ? "
                "AND (current_eligibility_status = 'eligible' OR current_eligibility_status IS NULL) "
                "ORDER BY employee_id"
                + (", plan_design_id" if "plan_design_id" in columns else ""),
                [year],
            ).fetchall()
            if not conn.execute(
                "SELECT 1 FROM fct_workforce_snapshot WHERE simulation_year = ? LIMIT 1",
                [year],
            ).fetchone():
                raise ValueError(f"No snapshot is available for year {year}")
            limits = _limits(conn, year)
        return (
            resolved,
            evidence,
            limits,
            [dict(zip(fields + optional, row)) for row in rows],
        )

    def _verify(
        self,
        workspace_id: str,
        scenario_id: str,
        expected: str,
        year: int,
        threshold: float,
    ) -> None:
        current = self.db_resolver.resolve(workspace_id, scenario_id)
        if not current.exists or _evidence(current, year, threshold) != expected:
            raise ComplianceEvidenceChangedError(
                "Results changed. Refresh the compliance overview."
            )

    def summary(
        self,
        workspace_id: str,
        scenario_id: str,
        name: str,
        year: int,
        threshold: float = 0.95,
    ) -> ComplianceSummary:
        resolved, evidence, limits, rows = self._read(
            workspace_id, scenario_id, year, threshold
        )
        employees = [_employee(row, limits, threshold) for row in rows]
        notes = self._notes(limits, employees, resolved)
        ndt = _ndt_coverage(
            self._ndt(resolved, workspace_id, scenario_id, name, year, threshold),
            rows,
            employees,
        )
        if not employees:
            notes.append(
                "No eligible employees are available for this year; no compliance result is asserted."
            )
        self._verify(workspace_id, scenario_id, evidence, year, threshold)
        return ComplianceSummary(
            scenario_id=scenario_id,
            scenario_name=name,
            year=year,
            run_id=resolved.run_id,
            evidence=evidence,
            warning_threshold=threshold,
            limits=limits,
            participant_count=len(employees),
            deferrals=_rollup(employees, "deferrals"),
            annual_additions=_rollup(employees, "annual_additions"),
            compensation=_rollup(employees, "compensation"),
            catch_up=_catch_up(employees, "ordinary"),
            super_catch_up=_catch_up(employees, "super"),
            ndt=ndt,
            notes=notes,
        )

    def employees(
        self,
        workspace_id: str,
        scenario_id: str,
        year: int,
        evidence: str,
        metric: MetricName,
        status: LimitStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        threshold: float = 0.95,
    ) -> ComplianceEmployeePage:
        self._verify(workspace_id, scenario_id, evidence, year, threshold)
        resolved, actual, limits, rows = self._read(
            workspace_id, scenario_id, year, threshold
        )
        if actual != evidence:
            raise ComplianceEvidenceChangedError(
                "Results changed. Refresh the compliance overview."
            )
        employees = [_employee(row, limits, threshold) for row in rows]
        if metric in ("catch_up", "super_catch_up"):
            group = "ordinary" if metric == "catch_up" else "super"
            employees = [e for e in employees if e.catch_up_group == group]
        elif status:
            field = {
                "402g": "deferrals",
                "415c": "annual_additions",
                "401a17": "compensation",
            }[metric]
            employees = [e for e in employees if getattr(e, field).status == status]
        self._verify(workspace_id, scenario_id, evidence, year, threshold)
        return ComplianceEmployeePage(
            evidence=evidence,
            total=len(employees),
            offset=offset,
            limit=limit,
            employees=employees[offset : offset + limit],
        )

    @staticmethod
    def _notes(
        limits: ComplianceLimits | None,
        employees: list[ComplianceEmployee],
        resolved: ResolvedDatabasePath,
    ) -> list[str]:
        notes = [
            "Catch-up usage is modeled from deferrals above the base limit using simulation age; other catch-up triggers are not modeled.",
            "415 uses the existing annualized compensation proxy; forfeitures and employee after-tax additions are excluded.",
            "401(a)(17) reports compensation-cap impact, not a compliance violation. A mid-year hire does not prorate the annual dollar cap.",
            "ADP uses current-year testing without a safe-harbor election; open ADP for alternate assumptions.",
        ]
        if limits is None:
            notes.append(
                "IRS limits are unavailable for this year. No limit result is asserted."
            )
        elif limits.differs_from_current_seed:
            notes.append(
                "Recorded limits differ from the current seed. Metrics retain the limits used by this run; rerun to use updated limits."
            )
        if limits and limits.is_estimated is None:
            notes.append(
                "The archive does not record whether these limits were estimated."
            )
        if any(e.age is None for e in employees):
            notes.append(
                "Age is unavailable for some employees; age-dependent metrics are unavailable."
            )
        if any(e.plan_design_id is None for e in employees):
            notes.append("Plan-design identity is unavailable in this legacy archive.")
        if resolved.run_warning:
            notes.append(
                "A simulation is in progress; this report uses the retained successful result."
            )
        return notes

    def _ndt(
        self,
        resolved: ResolvedDatabasePath,
        workspace_id: str,
        scenario_id: str,
        name: str,
        year: int,
        threshold: float,
    ) -> list[ComplianceNDTResult]:
        service = NDTService(self.storage, db_resolver=_PinnedResolver(resolved))
        arguments = (workspace_id, scenario_id, name, year)
        results: list[
            ADPScenarioResult | ACPScenarioResult | Section415ScenarioResult
        ] = [
            service.run_adp_test(*arguments),
            service.run_acp_test(*arguments),
            service.run_415_test(*arguments, warning_threshold=threshold),
        ]
        return [
            ComplianceNDTResult(
                test_type=kind,
                result=result.test_result,
                message=result.test_message,
                margin=getattr(result, "margin", None),
            )
            for kind, result in zip(("adp", "acp", "415"), results)
        ]
