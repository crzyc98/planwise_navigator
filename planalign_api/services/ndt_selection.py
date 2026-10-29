"""Request-local NDT population selection; archived tables remain read-only."""

import duckdb
import yaml

from .database_path_resolver import ResolvedDatabasePath


def _configured_scenario(
    connection: duckdb.DuckDBPyConnection, resolved: ResolvedDatabasePath
) -> str:
    """Bind the snapshot identity to archived configuration when available."""
    columns = {
        row[0]
        for row in connection.execute("DESCRIBE fct_workforce_snapshot").fetchall()
    }
    if not {"scenario_id", "plan_design_id"} <= columns:
        raise ValueError(
            "NDT design selection unavailable for legacy unscoped snapshots"
        )
    scopes = connection.execute(
        "SELECT DISTINCT scenario_id FROM fct_workforce_snapshot"
    ).fetchall()
    if len(scopes) != 1 or scopes[0][0] is None or not str(scopes[0][0]).strip():
        raise ValueError(
            "NDT selection requires one known configured scenario in the archive"
        )
    scenario = str(scopes[0][0])
    if resolved.config_path is not None:
        config = yaml.safe_load(resolved.config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("NDT archived configuration is not a mapping")
        # Match config/export.py: omitted/empty scenario ID exports as default.
        expected = config.get("scenario_id") or "default"
        if scenario != expected:
            raise ValueError(
                "NDT snapshot scenario does not match archived configuration"
            )
    return scenario


def _validate_design_identity(
    connection: duckdb.DuckDBPyConnection, bounds: tuple[int, int] | None
) -> None:
    predicate = "" if bounds is None else " AND simulation_year BETWEEN ? AND ?"
    unknown = connection.execute(
        "SELECT COUNT(*) FROM fct_workforce_snapshot "
        "WHERE (plan_design_id IS NULL OR trim(plan_design_id) = '')" + predicate,
        [] if bounds is None else list(bounds),
    ).fetchone()[0]
    if unknown:
        raise ValueError("NDT selected history contains unknown plan_design_id")


def select_ndt_design(
    connection: duckdb.DuckDBPyConnection,
    resolved: ResolvedDatabasePath,
    plan_design_id: str | None,
    year: int | None = None,
    lookback: int = 2,
) -> None:
    """Scope every request query without modifying the read-only archive.

    The temporary snapshot prevents downstream queries and validators from
    accidentally joining another design. Only required years are materialized.
    Closing the per-request connection discards it.
    """
    if plan_design_id is None:
        return
    if not plan_design_id.strip() or resolved.source not in ("run", "scenario"):
        raise ValueError(
            "NDT selection requires a nonblank design and a scenario/run archive"
        )
    scenario = _configured_scenario(connection, resolved)
    bounds = None if year is None else (year - lookback, year)
    _validate_design_identity(connection, bounds)
    database = connection.execute("SELECT current_database()").fetchone()[0]
    catalog = '"' + database.replace('"', '""') + '"'
    years = "" if bounds is None else " AND simulation_year BETWEEN ? AND ?"
    connection.execute(
        f"CREATE TEMP TABLE fct_workforce_snapshot AS SELECT * FROM {catalog}.main.fct_workforce_snapshot "
        "WHERE scenario_id = ? AND plan_design_id = ?" + years,
        [scenario, plan_design_id] + ([] if bounds is None else list(bounds)),
    )
    predicate = "" if year is None else " WHERE simulation_year = ?"
    count = connection.execute(
        "SELECT COUNT(*) FROM fct_workforce_snapshot" + predicate,
        [] if year is None else [year],
    ).fetchone()[0]
    if not count:
        raise ValueError(
            "NDT selected design has no population for the requested year(s)"
        )


def available_ndt_designs(connection: duckdb.DuckDBPyConnection) -> list[str]:
    """Candidate IDs only; each determination still validates selected history."""
    columns = {
        row[0]
        for row in connection.execute("DESCRIBE fct_workforce_snapshot").fetchall()
    }
    if "plan_design_id" not in columns:
        return []
    return [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT plan_design_id FROM fct_workforce_snapshot "
            "WHERE plan_design_id IS NOT NULL AND trim(plan_design_id) <> '' ORDER BY plan_design_id"
        ).fetchall()
    ]
