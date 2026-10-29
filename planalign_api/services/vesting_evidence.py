"""Validate the source grain and operands actually consumed by vesting."""

import duckdb


class VestingEvidenceError(ValueError):
    """The selected contribution history cannot support a projection."""


def vesting_scope_columns(connection: duckdb.DuckDBPyConnection) -> list[str]:
    columns = {
        row[0]
        for row in connection.execute("DESCRIBE fct_workforce_snapshot").fetchall()
    }
    return [name for name in ("scenario_id", "plan_design_id") if name in columns]


def validate_vesting_history(
    connection: duckdb.DuckDBPyConnection, where_clause: str = ""
) -> None:
    """Validate selected terminations and their same-scope prior active rows.

    Cohort filters apply to terminations, not prior years: an employee's earlier
    contributions remain relevant even if their earlier cohort attributes differ.
    Legacy archives without scope columns retain employee/year identity.
    """
    scope = vesting_scope_columns(connection)
    keys = scope + ["employee_id"]
    # A NULL scope key on a prior row must reach the identity check below
    # rather than silently falling out of the same-scope join.
    join = " AND ".join(
        [f"(s.{key} IS NULL OR s.{key} = t.{key})" for key in scope]
        + ["s.employee_id = t.employee_id"]
    )
    nulls = " OR ".join(f"{key} IS NULL" for key in keys)
    group = ", ".join(keys + ["simulation_year"])
    cte = f"""WITH terminated AS (
        SELECT * FROM fct_workforce_snapshot {where_clause}
        {"AND" if where_clause else "WHERE"} UPPER(employment_status) = 'TERMINATED'
    ), relevant AS (
        SELECT s.* FROM fct_workforce_snapshot s WHERE EXISTS (
            SELECT 1 FROM terminated t WHERE {join}
            AND ((s.simulation_year < t.simulation_year AND UPPER(s.employment_status) = 'ACTIVE')
                 OR s.simulation_year = t.simulation_year
                 OR s.simulation_year IS NULL)
        )
    ) """
    bad_keys = connection.execute(cte + f"""
        SELECT COUNT(*) FROM (SELECT {group} FROM relevant GROUP BY {group}
        HAVING COUNT(*) > 1 OR {nulls} OR simulation_year IS NULL)
        """).fetchone()[0]
    if bad_keys:
        raise VestingEvidenceError(
            "Vesting basis unavailable: duplicate or missing snapshot identity in selected history"
        )
    invalid = connection.execute(cte + """
        SELECT COUNT(*) FROM relevant s WHERE UPPER(s.employment_status) = 'ACTIVE'
        AND (total_employer_contributions IS NULL
             OR NOT isfinite(total_employer_contributions) OR total_employer_contributions < 0)
        """).fetchone()[0]
    if invalid:
        raise VestingEvidenceError(
            "Vesting basis unavailable: missing or invalid prior employer contributions"
        )
