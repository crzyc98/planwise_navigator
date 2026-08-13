"""Read-only target validation and evidence-pack assembly."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence

import duckdb

from planalign_ensemble.models import METRIC_REGISTRY

from .decompose import build_executive_summary, decompose_row
from .models import EvidencePack, PackProvenance, PackWarning
from .queries import build_metric_query


SNAPSHOT_TABLE = "fct_workforce_snapshot"


class EvidenceError(RuntimeError):
    """Base error for deterministic evidence generation."""


class EvidenceNotFoundError(EvidenceError):
    """The requested result store does not exist."""


class UnsupportedEvidenceError(EvidenceError):
    """The result cannot support the requested evidence pack."""

    def __init__(
        self,
        message: str,
        *,
        available_years: tuple[int, ...] = (),
        missing_columns: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.available_years = available_years
        self.missing_columns = missing_columns


class EvidenceConflictError(EvidenceError):
    """The result cannot be read consistently, usually because it is locked."""


@dataclass(frozen=True)
class TargetSupport:
    columns: frozenset[str]
    available_years: tuple[int, ...]


@dataclass(frozen=True)
class EvidenceTarget:
    database_path: Path
    result_store: str
    scenario_id: str
    run_id: str
    workspace_id: str | None = None
    scenario_name: str | None = None
    active_run_id: str | None = None
    run_dir: Path | None = None

    def __post_init__(self) -> None:
        logical = PurePosixPath(self.result_store)
        if (
            logical.is_absolute()
            or ".." in logical.parts
            or logical.name != "simulation.duckdb"
        ):
            raise ValueError("result_store must be a contained run-relative locator")

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if not self.database_path.is_file():
            raise EvidenceNotFoundError(
                f"Result database not found: {self.result_store}"
            )
        try:
            with duckdb.connect(str(self.database_path), read_only=True) as connection:
                yield connection
        except EvidenceError:
            raise
        except duckdb.Error as exc:
            text = str(exc).lower()
            if "lock" in text or "conflicting" in text:
                raise EvidenceConflictError(
                    f"Result store is locked and cannot be read safely: {self.result_store}"
                ) from exc
            raise UnsupportedEvidenceError(
                f"Result store is not a readable DuckDB database: {self.result_store}"
            ) from exc

    def inspect(self) -> TargetSupport:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_name = ?",
                [SNAPSHOT_TABLE],
            ).fetchone()
            if exists is None:
                raise UnsupportedEvidenceError(
                    f"Required table {SNAPSHOT_TABLE} is unavailable"
                )
            columns = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'main' AND table_name = ?",
                    [SNAPSHOT_TABLE],
                ).fetchall()
            )
            if "simulation_year" not in columns:
                raise UnsupportedEvidenceError(
                    "Required column simulation_year is unavailable",
                    missing_columns=("simulation_year",),
                )
            years = tuple(
                int(row[0])
                for row in connection.execute(
                    f"SELECT DISTINCT simulation_year FROM {SNAPSHOT_TABLE} "
                    "ORDER BY simulation_year"
                ).fetchall()
            )
        return TargetSupport(columns=columns, available_years=years)

    def signature(self) -> tuple[int, int]:
        stat = self.database_path.stat()
        return stat.st_size, stat.st_mtime_ns


def build_evidence_pack(
    target: EvidenceTarget,
    metric: str,
    base_year: int,
    target_year: int,
    *,
    provenance: PackProvenance | None = None,
    warnings: Sequence[PackWarning] = (),
) -> EvidencePack:
    """Build one deterministic pack without modifying its bound result store."""
    if metric not in METRIC_REGISTRY:
        raise UnsupportedEvidenceError(
            f"Unsupported metric {metric}; available metrics: {', '.join(METRIC_REGISTRY)}"
        )
    if base_year >= target_year:
        raise UnsupportedEvidenceError("base_year must be earlier than target_year")
    before = target.signature()
    support = target.inspect()
    missing = tuple(
        column
        for column in METRIC_REGISTRY[metric].required_columns
        if column not in support.columns
    )
    if missing:
        raise UnsupportedEvidenceError(
            f"Metric {metric} is unavailable; missing columns: {', '.join(missing)}",
            available_years=support.available_years,
            missing_columns=missing,
        )
    requested = {base_year, target_year}
    if not requested.issubset(support.available_years):
        available = ", ".join(str(year) for year in support.available_years) or "none"
        raise UnsupportedEvidenceError(
            f"Requested years are unavailable; available years: {available}",
            available_years=support.available_years,
        )
    query = build_metric_query(metric, base_year, target_year, support.columns)
    with target.connect() as connection:
        cursor = connection.execute(query)
        values = cursor.fetchone()
        assert values is not None
        description = cursor.description
        assert description is not None
        row = dict(zip((item[0] for item in description), values, strict=True))
        resolved_provenance = provenance or _read_provenance(connection, target)
    if row["base_value"] is None or row["target_value"] is None:
        raise UnsupportedEvidenceError(
            f"Metric {metric} has an undefined endpoint population for {base_year} or {target_year}",
            available_years=support.available_years,
        )
    if target.signature() != before:
        raise EvidenceConflictError(
            "Result store changed during the read-only evidence request"
        )
    change, drivers, residual, arithmetic_warnings = decompose_row(
        metric,
        base_year,
        target_year,
        row,
        query=query,
        result_store=target.result_store,
    )
    ordered_warnings = tuple(
        sorted((*warnings, *arithmetic_warnings), key=_warning_key)
    )
    return EvidencePack(
        provenance=resolved_provenance,
        change=change,
        drivers=drivers,
        residual=residual,
        warnings=ordered_warnings,
        executive_summary=build_executive_summary(change, drivers),
        population_note=(
            "Canonical snapshot populations include all rows for compensation, employer cost, participation, and average deferral; "
            "only active headcount filters employment status. Entering and leaving refer to snapshot membership, while retained records persist across both selected years."
        ),
    )


def _read_provenance(
    connection: duckdb.DuckDBPyConnection, target: EvidenceTarget
) -> PackProvenance:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    row = None
    if "run_metadata" in tables:
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = 'run_metadata'"
            ).fetchall()
        }
        seed_column = (
            "random_seed"
            if "random_seed" in columns
            else "seed"
            if "seed" in columns
            else "NULL"
        )
        if target.run_id != "legacy" and "run_id" in columns:
            row = connection.execute(
                f"SELECT run_timestamp, {seed_column}, config_fingerprint FROM run_metadata WHERE run_id = ? ORDER BY run_timestamp DESC LIMIT 1",
                [target.run_id],
            ).fetchone()
        if row is None:
            row = connection.execute(
                f"SELECT run_timestamp, {seed_column}, config_fingerprint FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1"
            ).fetchone()
    timestamp, seed, fingerprint = row if row else (None, None, None)
    return PackProvenance(
        workspace_id=target.workspace_id,
        scenario_id=target.scenario_id,
        scenario_name=target.scenario_name,
        run_id=target.run_id,
        run_timestamp=timestamp,
        random_seed=seed,
        config_fingerprint=fingerprint
        if fingerprint and len(str(fingerprint)) == 64
        else None,
        result_store=target.result_store,
        verification_disposition="unverifiable"
        if target.run_id == "legacy"
        else "fully_verified",
    )


def _warning_key(warning: PackWarning) -> tuple[int, str]:
    severity = {"critical": 0, "caution": 1, "info": 2}
    return severity[warning.severity], warning.code


__all__ = [
    "EvidenceConflictError",
    "EvidenceError",
    "EvidenceNotFoundError",
    "EvidenceTarget",
    "TargetSupport",
    "UnsupportedEvidenceError",
    "build_evidence_pack",
]
