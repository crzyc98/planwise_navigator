"""Evidence checks on annual snapshot operands used by NDT calculations."""

from typing import Literal

import duckdb

NDTKind = Literal["adp", "acp", "401a4", "415"]
AFTER_TAX_COLUMNS = (
    "employee_after_tax_contributions",
    "employee_after_tax_contribution",
    "after_tax_contributions",
    "after_tax_contribution",
)


def validate_ndt_inputs(
    connection: duckdb.DuckDBPyConnection,
    year: int,
    kind: NDTKind,
    prior_baseline: bool = False,
) -> None:
    """Reject unknown operands and unsupported zero-denominator determinations."""
    validate_eligibility_and_denominator(connection, year, kind)
    fields = _used_fields(connection, kind, prior_baseline)
    if kind != "415":
        validate_classification_pay(connection, year)
    predicate = "simulation_year = ? AND (current_eligibility_status = 'eligible' OR current_eligibility_status IS NULL)"
    for field in fields:
        count = connection.execute(
            f"SELECT COUNT(*) FROM fct_workforce_snapshot WHERE {predicate} "
            f"AND ({field} IS NULL OR NOT isfinite({field}) OR {field} < 0)",
            [year],
        ).fetchall()[0][0]
        if count:
            raise ValueError(
                f"NDT input unavailable: {count} eligible row(s) have missing or invalid {field} in {year}"
            )
    if (
        kind == "415"
        and not connection.execute(
            f"SELECT COUNT(*) FROM fct_workforce_snapshot WHERE {predicate}",
            [year],
        ).fetchall()[0][0]
    ):
        raise ValueError(f"NDT input unavailable: no eligible population in {year}")


def validate_ndt_population(
    connection: duckdb.DuckDBPyConnection, year: int, lookback: int
) -> None:
    """Require one unambiguous snapshot population for this selector-free API."""
    columns = {
        row[0]
        for row in connection.execute("DESCRIBE fct_workforce_snapshot").fetchall()
    }
    bounds = [year - lookback, year]
    for column in ("scenario_id", "plan_design_id"):
        if column not in columns:
            continue  # Legacy archives are supported only at unique employee/year grain.
        scopes = connection.execute(
            f"SELECT DISTINCT {column} FROM fct_workforce_snapshot "
            "WHERE simulation_year BETWEEN ? AND ?",
            bounds,
        ).fetchall()
        if any(value is None or not str(value).strip() for (value,) in scopes):
            raise ValueError(
                f"NDT population unavailable: missing {column} in selected snapshot history"
            )
        if len(scopes) > 1:
            raise ValueError(
                f"NDT population unavailable: multiple {column} values; "
                "design/scenario selection is not supported by this endpoint"
            )
    invalid = connection.execute(
        "SELECT COUNT(*) FROM (SELECT employee_id, simulation_year "
        "FROM fct_workforce_snapshot WHERE simulation_year BETWEEN ? AND ? "
        "GROUP BY employee_id, simulation_year "
        "HAVING COUNT(*) > 1 OR employee_id IS NULL)",
        bounds,
    ).fetchall()[0][0]
    if invalid:
        raise ValueError(
            "NDT population unavailable: duplicate or missing employee/year keys "
            "in the selected snapshot history"
        )


def validate_classification_pay(
    connection: duckdb.DuckDBPyConnection, year: int
) -> None:
    """Check the exact prior-pay or fallback operand used for classification."""
    invalid = connection.execute(
        """SELECT COUNT(*) FROM fct_workforce_snapshot s
        LEFT JOIN fct_workforce_snapshot p
          ON s.employee_id = p.employee_id AND p.simulation_year = ?
        WHERE s.simulation_year = ?
          AND (s.current_eligibility_status = 'eligible' OR s.current_eligibility_status IS NULL)
          AND (COALESCE(p.current_compensation, s.current_compensation) IS NULL
               OR NOT isfinite(COALESCE(p.current_compensation, s.current_compensation))
               OR COALESCE(p.current_compensation, s.current_compensation) < 0)""",
        [year - 1, year],
    ).fetchall()[0][0]
    if invalid:
        raise ValueError(
            f"NDT input unavailable: {invalid} eligible row(s) have invalid HCE classification compensation in {year}"
        )


def _used_fields(
    connection: duckdb.DuckDBPyConnection, kind: NDTKind, prior_baseline: bool
) -> list[str]:
    fields = {
        "adp": [
            "prorated_annual_compensation",
            "prorated_annual_contributions",
            "employer_match_amount",
            "employer_core_amount",
        ],
        "acp": ["prorated_annual_compensation", "employer_match_amount"],
        "401a4": ["prorated_annual_compensation", "employer_core_amount"],
        "415": [
            "current_compensation",
            "prorated_annual_contributions",
            "employer_match_amount",
            "employer_core_amount",
        ],
    }[kind]
    if prior_baseline:
        fields = ["prorated_annual_compensation", "prorated_annual_contributions"]
    if kind == "401a4":
        fields.append("employer_match_amount")
    if kind == "acp":
        columns = {
            row[0]
            for row in connection.execute("DESCRIBE fct_workforce_snapshot").fetchall()
        }
        fields.extend(
            next(([name] for name in AFTER_TAX_COLUMNS if name in columns), [])
        )
    return fields


def validate_eligibility_and_denominator(
    connection: duckdb.DuckDBPyConnection, year: int, kind: NDTKind
) -> None:
    """Do not infer eligibility or silently discard zero-denominator employees."""
    unknown = connection.execute(
        """SELECT COUNT(*) FROM fct_workforce_snapshot
        WHERE simulation_year = ? AND (current_eligibility_status IS NULL
          OR current_eligibility_status NOT IN ('eligible', 'ineligible', 'pending'))""",
        [year],
    ).fetchall()[0][0]
    if unknown:
        raise ValueError(
            f"NDT input unavailable: {unknown} row(s) have unknown eligibility in {year}"
        )
    denominator = (
        "current_compensation" if kind == "415" else "prorated_annual_compensation"
    )
    zero = connection.execute(
        f"SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ? "
        f"AND current_eligibility_status = 'eligible' AND {denominator} = 0",
        [year],
    ).fetchall()[0][0]
    if zero:
        raise ValueError(
            f"NDT input unavailable: {zero} eligible row(s) have zero {denominator} "
            f"in {year}; no exclusion policy or zero-denominator determination is established"
        )
