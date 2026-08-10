"""Output/database path resolution shared by the CLI and API surfaces.

``run_optimizer`` requires a fresh (empty or nonexistent) ``database_dir`` —
unlike calibration's serialize-on-a-shared-DB model, a second run can never
usefully wait for a directory to become fresh, so both the CLI and the API
router must reject non-fresh targets with the same rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def resolve_output_paths(
    database: Path | None, output: Path | None
) -> tuple[Path, Path]:
    default = Path("var/optimizer_runs") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    database_dir = (database or output or default).resolve()
    output_dir = (output or database_dir).resolve()
    shared = (Path("dbt") / "simulation.duckdb").resolve()
    for flag, path in (("--database", database_dir), ("--output", output_dir)):
        if path == shared or path.suffix == ".duckdb":
            raise ValueError(
                f"{flag} must be a fresh directory, never dbt/simulation.duckdb or another database file"
            )
    return database_dir, output_dir


def require_fresh_directory(path: Path, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"{label} directory is not empty: {path}")
