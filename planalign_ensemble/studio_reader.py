"""Read-only Studio access to a client-selected ensemble aggregate database.

Ensemble databases (``ensemble.duckdb``) are written by :mod:`.aggregate` and
:mod:`.attribution` and are never dbt models or the shared scenario database
(see ``docs/guides/seed_ensembles.md``). This module never writes to one.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict

from .models import (
    AttributionShare,
    MetricDistribution,
    MetricSeedValue,
    RiskStatement,
    Threshold,
)
from .risk import evaluate_thresholds

_SHARED_DEV_DATABASE = (Path("dbt") / "simulation.duckdb").resolve()
_REQUIRED_TABLE = "fct_metric_distributions"

_DISTRIBUTION_COLUMNS = (
    "ensemble_id",
    "scenario_id",
    "metric",
    "simulation_year",
    "p10",
    "p25",
    "p50",
    "p75",
    "p90",
    "mean",
    "stddev",
    "n_seeds",
    "n_seeds_requested",
    "is_sufficient",
    "percentile_method",
)

_ATTRIBUTION_COLUMNS = (
    "ensemble_id",
    "scenario_id",
    "metric",
    "simulation_year",
    "subsystem",
    "variance_share",
    "ci_low",
    "ci_high",
    "baseline_variance",
    "frozen_variance",
    "anchor_seeds",
    "n_anchors",
    "n_seeds",
    "bootstrap_iterations",
    "baselines_reused",
    "baselines_executed",
    "stochastic_status",
)


class InvalidEnsembleDatabaseError(ValueError):
    """Raised when a client-supplied path is not a usable ensemble database."""


class EnsembleDatabaseSummary(BaseModel):
    """One discovered ensemble database, for a Studio picker."""

    model_config = ConfigDict(frozen=True)

    database_path: str
    ensemble_ids: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    metrics: tuple[str, ...]
    min_simulation_year: int | None
    max_simulation_year: int | None
    modified_at: float
    size_bytes: int


def validate_ensemble_database(path: Path) -> Path:
    """Resolve and validate a client-supplied path before it is ever opened.

    Rejects anything that isn't an existing ``.duckdb`` file, the shared dev
    database, or a file lacking the ``fct_metric_distributions`` table --
    surfacing a clear 4xx-worthy error instead of a raw DuckDB failure.
    """
    resolved = path.resolve()
    if resolved.suffix != ".duckdb":
        raise InvalidEnsembleDatabaseError("database must be a .duckdb file")
    if resolved == _SHARED_DEV_DATABASE:
        raise InvalidEnsembleDatabaseError(
            "database must not be the shared dev database (dbt/simulation.duckdb)"
        )
    if not resolved.is_file():
        raise InvalidEnsembleDatabaseError(f"database does not exist: {resolved}")
    if not _has_table(resolved, _REQUIRED_TABLE):
        raise InvalidEnsembleDatabaseError(
            f"database is missing the '{_REQUIRED_TABLE}' table: {resolved}"
        )
    return resolved


def discover_ensemble_databases(root: Path) -> list[EnsembleDatabaseSummary]:
    """List ensemble databases under ``root``, skipping files that don't qualify."""
    if not root.is_dir():
        raise InvalidEnsembleDatabaseError(f"root is not a directory: {root}")
    summaries: list[EnsembleDatabaseSummary] = []
    for candidate in sorted(root.rglob("ensemble.duckdb")):
        try:
            validate_ensemble_database(candidate)
            summaries.append(_summarize(candidate))
        except (InvalidEnsembleDatabaseError, duckdb.Error):
            # A stray or corrupt file under the scan root must not break the
            # whole picker -- skip it rather than 500ing the entire listing.
            continue
    return summaries


def read_distributions(
    database: Path, scenario_id: str, ensemble_id: str
) -> list[MetricDistribution]:
    """Read distributions for one scenario/ensemble, ordered for stable display."""
    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            f"SELECT {', '.join(_DISTRIBUTION_COLUMNS)} FROM fct_metric_distributions "
            "WHERE scenario_id = ? AND ensemble_id = ? "
            "ORDER BY metric, simulation_year",
            [scenario_id, ensemble_id],
        ).fetchall()
    return [MetricDistribution(**dict(zip(_DISTRIBUTION_COLUMNS, row))) for row in rows]


def read_seed_values(
    database: Path, scenario_id: str, ensemble_id: str
) -> list[MetricSeedValue]:
    """Read per-seed evidence backing the distributions at the same grain."""
    with duckdb.connect(str(database), read_only=True) as connection:
        if not _has_table(database, "fct_metric_seed_values", connection=connection):
            return []
        rows = connection.execute(
            "SELECT ensemble_id, scenario_id, metric, simulation_year, seed, value "
            "FROM fct_metric_seed_values WHERE scenario_id = ? AND ensemble_id = ?",
            [scenario_id, ensemble_id],
        ).fetchall()
    columns = (
        "ensemble_id",
        "scenario_id",
        "metric",
        "simulation_year",
        "seed",
        "value",
    )
    return [MetricSeedValue(**dict(zip(columns, row))) for row in rows]


def read_risk_statements(
    database: Path,
    scenario_id: str,
    ensemble_id: str,
    thresholds: list[Threshold],
) -> list[RiskStatement]:
    """Evaluate ad hoc thresholds against stored evidence (thresholds aren't persisted)."""
    distributions = read_distributions(database, scenario_id, ensemble_id)
    seed_values = read_seed_values(database, scenario_id, ensemble_id)
    return evaluate_thresholds(distributions, seed_values, thresholds)


def read_attribution(
    database: Path, scenario_id: str, ensemble_id: str
) -> list[AttributionShare]:
    """Read variance attribution ranked like the Excel `Variance_Attribution` sheet."""
    with duckdb.connect(str(database), read_only=True) as connection:
        if not _has_table(database, "fct_variance_attribution", connection=connection):
            return []
        rows = connection.execute(
            f"SELECT {', '.join(_ATTRIBUTION_COLUMNS)} FROM fct_variance_attribution "
            "WHERE scenario_id = ? AND ensemble_id = ? "
            "ORDER BY metric, simulation_year, stochastic_status, "
            "variance_share DESC NULLS LAST, subsystem",
            [scenario_id, ensemble_id],
        ).fetchall()
    return [_to_attribution_share(row) for row in rows]


def _to_attribution_share(row: tuple) -> AttributionShare:
    fields = dict(zip(_ATTRIBUTION_COLUMNS, row))
    fields["anchor_seeds"] = tuple(
        int(seed) for seed in fields["anchor_seeds"].split(",") if seed
    )
    return AttributionShare(**fields)


def _summarize(database: Path) -> EnsembleDatabaseSummary:
    stat = database.stat()
    with duckdb.connect(str(database), read_only=True) as connection:
        sources = connection.execute(
            "SELECT DISTINCT ensemble_id, scenario_id FROM fct_metric_distributions"
        ).fetchall()
        metrics = connection.execute(
            "SELECT DISTINCT metric FROM fct_metric_distributions ORDER BY metric"
        ).fetchall()
        year_range = connection.execute(
            "SELECT MIN(simulation_year), MAX(simulation_year) "
            "FROM fct_metric_distributions"
        ).fetchone()
    return EnsembleDatabaseSummary(
        database_path=str(database),
        ensemble_ids=tuple(sorted({row[0] for row in sources})),
        scenario_ids=tuple(sorted({row[1] for row in sources})),
        metrics=tuple(row[0] for row in metrics),
        min_simulation_year=year_range[0] if year_range else None,
        max_simulation_year=year_range[1] if year_range else None,
        modified_at=stat.st_mtime,
        size_bytes=stat.st_size,
    )


def _has_table(
    path: Path, table: str, *, connection: duckdb.DuckDBPyConnection | None = None
) -> bool:
    if connection is not None:
        return _table_exists(connection, table)
    with duckdb.connect(str(path), read_only=True) as opened:
        return _table_exists(opened, table)


def _table_exists(connection: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        [table],
    ).fetchone()
    return row is not None


__all__ = [
    "EnsembleDatabaseSummary",
    "InvalidEnsembleDatabaseError",
    "discover_ensemble_databases",
    "read_attribution",
    "read_distributions",
    "read_risk_statements",
    "read_seed_values",
    "validate_ensemble_database",
]
