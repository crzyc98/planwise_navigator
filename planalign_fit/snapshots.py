"""Load, validate, and hash the historical census snapshots used for fitting.

A *snapshot* is one annual census file in the same schema the simulator already
consumes (``stg_census_data``). A *snapshot set* is 2-5 consecutive annual
snapshots; consecutive-year gaps are rejected because the cohort-linked diff in
:mod:`planalign_fit.transitions` assumes a one-year step.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb

SUPPORTED_SUFFIXES = (".parquet", ".csv")

MIN_SNAPSHOTS = 2
MAX_SNAPSHOTS = 5

# The fitter needs these to place an employee in an age x tenure x level cell.
REQUIRED_COLUMNS = (
    "employee_id",
    "employee_birth_date",
    "employee_hire_date",
    "employee_gross_compensation",
)

# Present-if-available columns. Each absent column disables a specific fit,
# which the report flags rather than silently defaulting.
OPTIONAL_COLUMNS = (
    "employee_termination_date",
    "active",
    "employee_deferral_rate",
    "employee_enrollment_date",
    "level_id",
)

_YEAR_PATTERN = re.compile(r"(19|20)\d{2}")
_YEAR_COLUMNS = ("snapshot_year", "simulation_year", "census_year", "plan_year")

_HASH_CHUNK_BYTES = 1 << 20


class SnapshotError(ValueError):
    """A snapshot directory could not be turned into a usable snapshot set."""


@dataclass(frozen=True)
class Snapshot:
    """One annual census file, with the provenance needed to reproduce a fit."""

    year: int
    path: Path
    sha256: str
    row_count: int
    columns: tuple[str, ...]

    @property
    def relation_name(self) -> str:
        return f"snapshot_{self.year}"

    def has(self, column: str) -> bool:
        return column in self.columns


@dataclass(frozen=True)
class SnapshotSet:
    """Consecutive annual snapshots, ordered oldest first."""

    snapshots: tuple[Snapshot, ...]

    def __iter__(self) -> Iterator[Snapshot]:
        return iter(self.snapshots)

    def __len__(self) -> int:
        return len(self.snapshots)

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(s.year for s in self.snapshots)

    @property
    def transition_years(self) -> tuple[int, ...]:
        """Years whose transitions are observable (every year but the first)."""
        return self.years[1:]

    @property
    def source_digest(self) -> str:
        """One digest over every source file, stable under reordering."""
        joined = "\n".join(f"{s.year}:{s.sha256}" for s in self.snapshots)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def common_columns(self) -> frozenset[str]:
        """Columns present in *every* snapshot — the only ones safe to diff."""
        sets = [frozenset(s.columns) for s in self.snapshots]
        return frozenset.intersection(*sets) if sets else frozenset()

    def supports(self, column: str) -> bool:
        return column in self.common_columns()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_expression(path: Path) -> str:
    """DuckDB scan expression for a snapshot file."""
    literal = str(path.resolve()).replace("'", "''")
    if path.suffix.lower() == ".parquet":
        return f"read_parquet('{literal}')"
    return f"read_csv_auto('{literal}', header=true, sample_size=-1)"


def _discover_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise SnapshotError(f"Snapshot directory not found: {directory}")
    files = sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise SnapshotError(
            f"No .parquet or .csv snapshots found in {directory}. "
            "Expected one census file per year."
        )
    return files


def _year_from_filename(path: Path) -> Optional[int]:
    found = {m.group(0) for m in _YEAR_PATTERN.finditer(path.stem)}
    if len(found) != 1:
        return None
    return int(found.pop())


def _year_from_column(
    conn: "duckdb.DuckDBPyConnection", path: Path, columns: Sequence[str]
) -> Optional[int]:
    for candidate in _YEAR_COLUMNS:
        if candidate not in columns:
            continue
        rows = conn.execute(
            f"SELECT DISTINCT CAST({candidate} AS INTEGER) FROM {read_expression(path)} "
            f"WHERE {candidate} IS NOT NULL"
        ).fetchall()
        years = {int(r[0]) for r in rows}
        if len(years) == 1:
            return years.pop()
        if len(years) > 1:
            raise SnapshotError(
                f"{path.name} carries multiple values in '{candidate}' ({sorted(years)}). "
                "Each snapshot file must cover exactly one year."
            )
    return None


def _describe(
    conn: "duckdb.DuckDBPyConnection", path: Path
) -> tuple[tuple[str, ...], int]:
    expression = read_expression(path)
    try:
        columns = tuple(
            str(row[0])
            for row in conn.execute(f"DESCRIBE SELECT * FROM {expression}").fetchall()
        )
        count_row = conn.execute(f"SELECT COUNT(*) FROM {expression}").fetchone()
    except Exception as exc:  # duckdb raises a family of IO/binder errors
        raise SnapshotError(f"Could not read snapshot {path.name}: {exc}") from exc
    if count_row is None:
        raise SnapshotError(f"Could not count rows in snapshot {path.name}.")
    return columns, int(count_row[0])


def _validate_columns(path: Path, columns: Sequence[str]) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise SnapshotError(
            f"{path.name} is missing required census column(s): {', '.join(missing)}. "
            "Snapshots must use the same schema as the simulator's census input."
        )


def _validate_set(snapshots: Sequence[Snapshot]) -> None:
    if len(snapshots) < MIN_SNAPSHOTS:
        raise SnapshotError(
            f"Fitting needs at least {MIN_SNAPSHOTS} consecutive annual snapshots; "
            f"found {len(snapshots)}. Transitions are only observable between years."
        )
    if len(snapshots) > MAX_SNAPSHOTS:
        raise SnapshotError(
            f"Fitting accepts at most {MAX_SNAPSHOTS} snapshots; found {len(snapshots)}. "
            "Trim the directory to the most recent years."
        )
    years = [s.year for s in snapshots]
    if len(set(years)) != len(years):
        duplicates = sorted({y for y in years if years.count(y) > 1})
        raise SnapshotError(
            f"Multiple snapshot files resolve to the same year(s): {duplicates}."
        )
    gaps = [(a, b) for a, b in zip(years, years[1:]) if b - a != 1]
    if gaps:
        rendered = ", ".join(f"{a}->{b}" for a, b in gaps)
        raise SnapshotError(
            f"Snapshot years must be consecutive; found gap(s): {rendered}. "
            "A cohort-linked diff assumes a one-year step."
        )


def load_snapshots(
    directory: Path | str,
    conn: "duckdb.DuckDBPyConnection",
) -> SnapshotSet:
    """Discover, validate, and hash every census snapshot in ``directory``.

    The year of each file comes from a year column when present, otherwise from
    an unambiguous four-digit year in the filename.
    """
    directory = Path(directory)
    snapshots: list[Snapshot] = []
    for path in _discover_files(directory):
        columns, row_count = _describe(conn, path)
        _validate_columns(path, columns)
        year = _year_from_column(conn, path, columns) or _year_from_filename(path)
        if year is None:
            raise SnapshotError(
                f"Could not determine the year of {path.name}. Name the file with a "
                "single four-digit year (e.g. census_2023.parquet) or include a "
                f"'{_YEAR_COLUMNS[0]}' column."
            )
        if row_count == 0:
            raise SnapshotError(f"Snapshot {path.name} is empty.")
        snapshots.append(
            Snapshot(
                year=year,
                path=path.resolve(),
                sha256=_sha256_file(path),
                row_count=row_count,
                columns=columns,
            )
        )

    snapshots.sort(key=lambda s: s.year)
    _validate_set(snapshots)
    return SnapshotSet(tuple(snapshots))


def register_snapshots(
    conn: "duckdb.DuckDBPyConnection", snapshot_set: SnapshotSet
) -> None:
    """Expose each snapshot as a DuckDB view named ``snapshot_<year>``."""
    for snapshot in snapshot_set:
        conn.execute(
            f"CREATE OR REPLACE VIEW {snapshot.relation_name} AS "
            f"SELECT * FROM {read_expression(snapshot.path)}"
        )
