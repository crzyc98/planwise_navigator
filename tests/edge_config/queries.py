"""Read-only targeted queries over completed simulation outputs."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any

import duckdb

from .assertions import TargetedAssertionResult
from .catalog import EdgeConfigScenario

CaseQuery = Callable[[EdgeConfigScenario, Path], list[tuple[str, dict[str, Any]]]]

# Deferral rates are stored as floats; compare with a tolerance, not equality.
TOLERANCE = 1e-9


def _query(
    database: Path, sql: str, params: list[Any] | None = None
) -> list[dict[str, Any]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        cursor = connection.execute(sql, params or [])
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute_violation_query(
    database: Path, sql: str, sample_limit: int = 20
) -> list[dict[str, Any]]:
    """Execute a caller-supplied read-only query with a hard diagnostic bound."""
    if not database.exists():
        raise FileNotFoundError(database)
    if not 1 <= sample_limit <= 20:
        raise ValueError("sample_limit must be between 1 and 20")
    return _query(database, f"SELECT * FROM ({sql}) violations LIMIT {sample_limit}")


def targeted_query(case: EdgeConfigScenario, database: Path) -> TargetedAssertionResult:
    """Run the boundary assertion selected by the catalog's assertion kind."""
    result = TargetedAssertionResult(
        case.name, case.boundary, case.assertion_kind, sample_limit=case.sample_limit
    )
    try:
        violations = ASSERTION_QUERIES[case.assertion_kind](case, database)
    except KeyError as error:
        raise ValueError(
            f"unsupported assertion kind: {case.assertion_kind}"
        ) from error
    for observed, row in violations:
        result.add(observed, row)
    result.observed = "no targeted violations" if result.passed else result.observed
    return result


def _grouped_employee_ids(case: EdgeConfigScenario) -> dict[str, str]:
    """Map fixture-only boundary labels to stable employee IDs for SQL filtering."""
    from tests.fixtures.edge_config_matrix import load_case_frame

    frame = load_case_frame(case)
    return dict(zip(frame["employee_id"], frame["boundary_group"]))


def _snapshot_rows(
    case: EdgeConfigScenario, database: Path, year: int
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    groups = _grouped_employee_ids(case)
    placeholders = ", ".join("?" for _ in groups)
    sql = (
        "SELECT * FROM fct_workforce_snapshot "
        f"WHERE simulation_year = ? AND employee_id IN ({placeholders})"
    )
    rows = _query(database, sql, [year, *groups])
    return groups, {row["employee_id"]: row for row in rows}


def _missing_group_rows(
    groups: dict[str, str], rows: dict[str, dict[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "boundary employee missing from snapshot",
            {"employee_id": employee_id, "group": group},
        )
        for employee_id, group in groups.items()
        if employee_id not in rows
    ]


def _cutoff_enrollment(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    groups, rows = _snapshot_rows(case, database, case.start_year)
    violations = _missing_group_rows(groups, rows)
    expected_enrollment = {"before_cutoff": False, "after_cutoff": True}
    for employee_id, group in groups.items():
        row = rows.get(employee_id)
        if row is None or group not in expected_enrollment:
            continue
        expected = expected_enrollment[group]
        enrolled = bool(row["is_enrolled_flag"])
        has_date = row["employee_enrollment_date"] is not None
        if enrolled != expected or has_date != expected:
            violations.append((f"{group} enrollment did not match cutoff", row))
    return violations


def _eligibility_suppression(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    groups, rows = _snapshot_rows(case, database, case.start_year)
    violations = _missing_group_rows(groups, rows)
    # Production reports a not-yet-eligible employee as 'pending', not
    # 'ineligible'. Scoped to the start year: eligibility state after the first
    # year is carried forward (#493) rather than re-determined.
    expected_status = {
        "suppressed_new_hire": "pending",
        "eligible_control": "eligible",
    }
    for employee_id, group in groups.items():
        row = rows.get(employee_id)
        if row is None or group not in expected_status:
            continue
        if row["current_eligibility_status"] != expected_status[group]:
            violations.append((f"{group} eligibility status was not preserved", row))
    return violations


def _tenure_match(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    groups, rows = _snapshot_rows(case, database, case.end_year)
    violations = _missing_group_rows(groups, rows)
    by_group = {group: rows.get(employee_id) for employee_id, group in groups.items()}
    short = by_group.get("short_service")
    long = by_group.get("long_service")
    if short is None or long is None:
        return violations
    if short["current_deferral_rate"] != long["current_deferral_rate"]:
        violations.append(
            (
                "comparison groups do not have equal deferral rates",
                {"short": short, "long": long},
            )
        )
    if long["employer_match_amount"] <= short["employer_match_amount"]:
        violations.append(
            (
                "long-service match was not greater than short-service match",
                {"short": short, "long": long},
            )
        )
    event_rows = _query(
        database,
        "SELECT employee_id, amount, simulation_year FROM fct_employer_match_events "
        "WHERE simulation_year = ? AND employee_id IN (?, ?)",
        [case.end_year, short["employee_id"], long["employee_id"]],
    )
    event_ids = {row["employee_id"] for row in event_rows}
    for employee_id in (short["employee_id"], long["employee_id"]):
        if employee_id not in event_ids:
            violations.append(
                (
                    "expected employer-match event was not emitted",
                    {"employee_id": employee_id},
                )
            )
    return violations


def _configured_escalation_cap(case: EdgeConfigScenario) -> float:
    """Read the ceiling from the case config rather than hardcoding it."""
    import yaml

    with case.config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    return float(config["deferral_auto_escalation"]["maximum_rate"])


def _escalation_group_violations(
    group: str, row: dict[str, Any], cap: float
) -> list[tuple[str, dict[str, Any]]]:
    original = float(row["original_deferral_rate"])
    rate = float(row["current_deferral_rate"])
    escalations = row["total_deferral_escalations"] or 0
    found: list[tuple[str, dict[str, Any]]] = []

    if group == "below_cap":
        if escalations < 1:
            found.append(("below-cap employee did not escalate", row))
        if rate <= original or rate > cap + TOLERANCE:
            found.append(("below-cap escalation did not stay within the cap", row))
    if group in {"at_cap", "above_cap"}:
        if escalations != 0:
            found.append(("cap-bound employee should not have escalated", row))
        if abs(rate - original) > TOLERANCE:
            found.append(("cap-bound employee's elected rate was not preserved", row))
    return found


def _escalation_cap(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    """The cap ceilings escalation, not the rate.

    int_deferral_rate_escalation_events preserves a rate already at or above the
    cap (`WHEN current_deferral_rate >= esc_cap THEN current_deferral_rate`)
    rather than clamping it down, so this is three statements, not one: below the
    cap escalates toward it, at the cap does not move, and above the cap the
    elected rate is left alone. Asserting a blanket "no rate exceeds the cap"
    would only pass if that preserve branch were broken.
    """
    groups, rows = _snapshot_rows(case, database, case.end_year)
    violations = _missing_group_rows(groups, rows)
    cap = _configured_escalation_cap(case)
    for employee_id, group in groups.items():
        row = rows.get(employee_id)
        if row is None:
            continue
        original = float(row["original_deferral_rate"])
        # Escalation never lifts anyone past the cap, but a pre-existing higher
        # elected rate is preserved, so the ceiling is max(cap, original).
        ceiling = max(cap, original) + TOLERANCE
        rate = float(row["current_deferral_rate"])
        effective_rate = float(row["effective_annual_deferral_rate"] or 0)
        if rate > ceiling or effective_rate > ceiling:
            violations.append(("deferral rate rose above the escalation ceiling", row))
        violations.extend(_escalation_group_violations(group, row, cap))
    return violations


def _zero_growth(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    groups, rows = _snapshot_rows(case, database, case.end_year)
    violations = _missing_group_rows(groups, rows)
    hires = _query(
        database,
        "SELECT employee_id, simulation_year FROM fct_yearly_events "
        "WHERE simulation_year BETWEEN ? AND ? AND event_type = 'hire'",
        [case.start_year, case.end_year],
    )
    for row in hires:
        violations.append(("zero-growth configuration emitted a hire", row))
    return violations


def _custom_hire_inputs(
    case: EdgeConfigScenario, database: Path
) -> list[tuple[str, dict[str, Any]]]:
    rows = _query(
        database,
        "SELECT employee_id, simulation_year, current_age, current_compensation "
        "FROM fct_workforce_snapshot WHERE simulation_year = ? "
        "AND employee_id LIKE 'NH_%'",
        [case.start_year],
    )
    if not rows:
        return [("custom new-hire configuration produced no hires", {})]
    violations: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        if row["current_age"] != 55:
            violations.append(("new hire did not use the configured age", row))
        if not 109000 <= row["current_compensation"] <= 131000:
            violations.append(
                ("new hire compensation ignored the configured range", row)
            )
    return violations


ASSERTION_QUERIES: dict[str, CaseQuery] = {
    "cutoff_enrollment": _cutoff_enrollment,
    "eligibility_suppression": _eligibility_suppression,
    "tenure_match": _tenure_match,
    "escalation_cap": _escalation_cap,
    "zero_growth": _zero_growth,
    "custom_hire_inputs": _custom_hire_inputs,
}
