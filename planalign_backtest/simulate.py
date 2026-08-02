"""Prepare and run one isolated backtest simulation per seed."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import duckdb
import yaml

from planalign_backtest.errors import SimulationFailure
from planalign_backtest.models import SeedRun, SnapshotSplit
from planalign_fit.apply import AppliedPack
from planalign_fit.snapshots import Snapshot
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import (
    ConstructionSpec,
    InitializationPolicy,
    build_orchestrator,
)


def prepare_boundary_census(snapshot: Snapshot, workdir: Path) -> Path:
    """Return a parquet census path without mutating the snapshot directory."""
    if snapshot.path.suffix.lower() == ".parquet":
        return snapshot.path
    workdir.mkdir(parents=True, exist_ok=True)
    destination = workdir / f"boundary_{snapshot.year}.parquet"
    source = str(snapshot.path.resolve()).replace("'", "''")
    target = str(destination.resolve()).replace("'", "''")
    with duckdb.connect(":memory:") as conn:
        columns = [
            str(row[0])
            for row in conn.execute(
                f"DESCRIBE SELECT * FROM read_csv_auto('{source}', header=true, "
                "sample_size=-1)"
            ).fetchall()
        ]
        projection = []
        for column in columns:
            quoted = '"' + column.replace('"', '""') + '"'
            if column == "employee_ssn":
                projection.append(
                    "COALESCE(CAST(employee_ssn AS VARCHAR), "
                    "CAST(employee_id AS VARCHAR)) AS employee_ssn"
                )
            else:
                projection.append(quoted)
        if "employee_ssn" not in columns:
            projection.append("CAST(employee_id AS VARCHAR) AS employee_ssn")
        if "employee_termination_date" not in columns:
            projection.append("CAST(NULL AS DATE) AS employee_termination_date")
        if "active" not in columns:
            projection.append("TRUE AS active")
        conn.execute(
            f"COPY (SELECT {', '.join(projection)} FROM "
            f"read_csv_auto('{source}', header=true, sample_size=-1)) "
            f"TO '{target}' (FORMAT PARQUET)"
        )
    return destination


def configure_seed(
    applied_pack: AppliedPack,
    split: SnapshotSplit,
    seed: int,
    boundary_census: Path,
    workdir: Path,
) -> AppliedPack:
    """Layer census, horizon, and seed over an applied pack's effective config."""
    raw = yaml.safe_load(applied_pack.config_path.read_text(encoding="utf-8")) or {}
    setup = raw.setdefault("setup", {})
    setup["census_parquet_path"] = str(boundary_census.resolve())
    setup["plan_year_start_date"] = f"{split.holdout_years[0]}-01-01"
    setup["plan_year_end_date"] = f"{split.holdout_years[0]}-12-31"
    simulation = raw.setdefault("simulation", {})
    simulation.update(
        {
            "random_seed": seed,
            "start_year": split.holdout_years[0],
            "end_year": split.holdout_years[-1],
        }
    )
    seed_dir = workdir / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    config_path = seed_dir / "effective_config.yaml"
    config_path.write_text(
        yaml.safe_dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    project_path = applied_pack.dbt_project_dir / "dbt_project.yml"
    project = yaml.safe_load(project_path.read_text(encoding="utf-8")) or {}
    project.setdefault("vars", {})[
        "simulation_effective_date"
    ] = f"{split.holdout_years[0]}-12-31"
    project_path.write_text(
        yaml.safe_dump(project, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return replace(applied_pack, config_path=config_path, workdir=seed_dir)


def run_seed(
    applied_pack: AppliedPack,
    split: SnapshotSplit,
    seed: int,
    workdir: Path,
) -> SeedRun:
    """Run exactly the held-out years in a fresh per-seed DuckDB."""
    database = workdir / f"seed_{seed}.duckdb"
    artifacts = workdir / f"seed_{seed}" / "dbt_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    config = load_simulation_config(applied_pack.config_path, env_overrides=False)
    try:
        built = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                dbt_project_dir=applied_pack.dbt_project_dir,
                dbt_artifacts_dir=artifacts,
                reports_dir=workdir / f"seed_{seed}" / "reports",
                initialization=InitializationPolicy.SELF_HEALING,
                entry_point="backtest",
                validation_mode=True,
                verbose=False,
            )
        )
        built.orchestrator.execute_multi_year_simulation(
            start_year=split.holdout_years[0],
            end_year=split.holdout_years[-1],
            fail_on_validation_error=True,
        )
    except Exception as exc:
        failed_year = int(getattr(exc, "year", split.holdout_years[0]))
        raise SimulationFailure(seed, failed_year, str(exc)) from exc
    with duckdb.connect(str(database), read_only=True) as conn:
        row = conn.execute(
            "SELECT config_fingerprint FROM run_metadata "
            "ORDER BY run_timestamp DESC LIMIT 1"
        ).fetchone()
    fingerprint = str(row[0]) if row else ""
    return SeedRun(
        seed=seed,
        database=database,
        config_fingerprint=fingerprint,
        years_simulated=split.holdout_years,
    )
