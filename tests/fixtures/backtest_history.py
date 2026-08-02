"""Simulator-generated annual history used to certify the backtest harness.

FR-030 asks the self-test to backtest *history the simulator itself produced*.
That framing is load-bearing rather than incidental: when the history comes from
the simulator under the same base config the backtest will later run, every
input the fitter does **not** fit — new-hire age distribution, auto-enrollment
policy, job-level compensation ranges — agrees on both sides by construction.
Any residual error is then attributable to the harness, which is the only thing
the self-test exists to certify.

The #458 fixture (:mod:`tests.fixtures.synthetic_census`) deliberately avoids
the simulator so the *fitter* can be graded independently of the thing it
configures. Reusing it here would grade the harness against a population evolved
by different rules, and a large error could not be attributed: harness bug,
fitter limitation, and generator/config divergence all look identical. Removing
that ambiguity is the whole point of this module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

from planalign_backtest.simulate import prepare_boundary_census
from planalign_fit.snapshots import Snapshot
from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import InitializationPolicy

from tests.fixtures.synthetic_census import TruthRates, generate_history

# Metrics must land inside this tolerance when the harness scores the simulator
# against its own output. Not zero: the parameters are estimated from three years
# of a finite population, so recovery is close but not exact.
SELF_TEST_TOLERANCE = 0.005

# Job-level headcount gets a wider band, and only because of how it is derived.
# Level is a *bucketing* of compensation, and compensation itself carries the
# ~0.5% error above. Employees sitting near a band boundary flip buckets on that
# margin, so a continuous error of a half percent emerges as a few percent in the
# per-level counts. Age and tenure bands do not need the allowance — those bucket
# integers that both sides compute identically, and they come out exact.
SELF_TEST_BUCKET_TOLERANCE = 0.05
SELF_TEST_BUCKET_PREFIX = "headcount.by_level."

# Census schema, in the column order `stg_census_data` expects.
CENSUS_COLUMNS = (
    "employee_id",
    "employee_birth_date",
    "employee_hire_date",
    "employee_termination_date",
    "employee_gross_compensation",
    "active",
    "level_id",
    "employee_deferral_rate",
    "employee_enrollment_date",
)

BASE_CONFIG = Path("config/simulation_config.yaml")
DBT_ROOT = Path("dbt").resolve()


@dataclass(frozen=True)
class SimulatedHistory:
    """Annual census snapshots exported from one real simulation run."""

    directory: Path
    years: tuple[int, ...]
    database: Path
    config_path: Path


def generate_backtest_history(
    directory: Path,
    *,
    start_year: int = 2025,
    years: int = 4,
    seed_headcount: int = 1_500,
) -> SimulatedHistory:
    """Run a real simulation and export each year's workforce as a census."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    workdir = (directory.parent / "_simulated_source").resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    end_year = start_year + years - 1
    # The census describes the population entering the first simulated year, so
    # it is stamped one year earlier. Feeding a year-N census and simulating
    # year N produces an empty fct_workforce_snapshot: the baseline is built for
    # N but no year is actually simulated forward into it.
    seed_census = _write_seed_census(workdir, seed_headcount, start_year - 1)
    database = (workdir / "history.duckdb").resolve()

    # One single-year run per year, each starting from the previous year's
    # exported census — the same census-in / snapshot-out shape the backtest
    # itself uses. Two things make the chained form necessary rather than
    # merely tidy: `fct_workforce_snapshot` does not retain every simulated
    # year (a 2022-2025 run leaves only 2024 and 2025), and a run only produces
    # a snapshot when its census describes the *preceding* year.
    exported: list[int] = []
    census = seed_census
    for year in range(start_year, end_year + 1):
        config_path = _write_config(workdir, census, year)
        built = build_orchestrator(
            ConstructionSpec(
                config=load_simulation_config(config_path, env_overrides=False),
                database=(workdir / f"year_{year}.duckdb").resolve(),
                threads=1,
                dbt_project_dir=_overlay_project(workdir, year),
                dbt_artifacts_dir=workdir / "dbt_artifacts",
                reports_dir=workdir / "reports",
                initialization=InitializationPolicy.SELF_HEALING,
                entry_point="backtest",
                validation_mode=True,
            )
        )
        built.orchestrator.execute_multi_year_simulation(
            start_year=year,
            end_year=year,
            fail_on_validation_error=True,
        )
        census_csv = _export_year(
            (workdir / f"year_{year}.duckdb").resolve(), directory, year
        )
        exported.append(year)
        census = prepare_boundary_census(
            Snapshot(year=year, path=census_csv, sha256="", row_count=0, columns=()),
            workdir / f"chain_{year}",
        ).resolve()
    database = (workdir / f"year_{end_year}.duckdb").resolve()
    return SimulatedHistory(
        directory=directory,
        years=tuple(exported),
        database=database,
        config_path=config_path,
    )


def _write_seed_census(workdir: Path, headcount: int, start_year: int) -> Path:
    """A year-zero population for the simulation to start from.

    Only this starting population comes from the synthetic generator; every
    later year is the simulator's own output. A plausible census is all that is
    required here — it need not have been evolved under known rates.
    """
    staging = workdir / "seed_history"
    generate_history(
        staging,
        headcount=headcount,
        years=1,
        start_year=start_year,
        truth=TruthRates(),
    )
    # Reuse the backtest's own CSV->parquet preparation rather than a plain
    # SELECT *: it synthesizes the employee_ssn that stg_census_data requires
    # and is NOT NULL on, so a hand-rolled copy fails at staging. Only `path`
    # and `year` are read, and load_snapshots refuses a single-file directory,
    # so the descriptor is built directly.
    source = sorted(staging.glob("census_*.csv"))[0]
    snapshot = Snapshot(
        year=start_year,
        path=source.resolve(),
        sha256="",
        row_count=headcount,
        columns=(),
    )
    return prepare_boundary_census(snapshot, workdir).resolve()


def _overlay_project(workdir: Path, year: int) -> Path:
    """A dbt project identical to the real one but pinned to ``year``.

    `dbt/dbt_project.yml` hard-codes `simulation_effective_date: '2024-12-31'`.
    Simulating any other year against it yields an *empty*
    `fct_workforce_snapshot` while events still generate normally — a silent
    failure. The backtest avoids this by patching the var into the pack's
    overlay project; the fixture needs the same treatment without a pack, and
    must not mutate the checked-in project to get it.
    """
    overlay = workdir / f"project_{year}"
    overlay.mkdir(parents=True, exist_ok=True)
    project = yaml.safe_load((DBT_ROOT / "dbt_project.yml").read_text(encoding="utf-8"))
    project.setdefault("vars", {})["simulation_effective_date"] = f"{year}-12-31"
    project["vars"]["simulation_start_year"] = year
    project["vars"]["simulation_end_year"] = year
    (overlay / "dbt_project.yml").write_text(
        yaml.safe_dump(project, sort_keys=False), encoding="utf-8"
    )
    for entry in (
        "analyses",
        "macros",
        "models",
        "seeds",
        "snapshots",
        "tests",
        "packages.yml",
        "package-lock.yml",
        "dbt_packages",
    ):
        source = DBT_ROOT / entry
        destination = overlay / entry
        if source.exists() and not destination.exists():
            destination.symlink_to(source, target_is_directory=source.is_dir())
    return overlay


def _write_config(workdir: Path, census: Path, year: int) -> Path:
    """The base config, pointed at one census and one simulated year.

    The plan-year dates must move with the year. Left at the base config's own
    values, a run for a different year produces an empty snapshot.
    """
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8")) or {}
    setup = config.setdefault("setup", {})
    setup["census_parquet_path"] = str(census)
    setup["plan_year_start_date"] = f"{year}-01-01"
    setup["plan_year_end_date"] = f"{year}-12-31"
    simulation = config.setdefault("simulation", {})
    simulation["start_year"] = year
    simulation["end_year"] = year
    destination = workdir / f"config_{year}.yaml"
    destination.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return destination


def _export_year(database: Path, directory: Path, year: int) -> Path:
    """Write one year's workforce as a census CSV from `fct_workforce_snapshot`."""
    with duckdb.connect(str(database), read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT
              employee_id,
              CAST(employee_birth_date AS VARCHAR),
              CAST(employee_hire_date AS VARCHAR),
              CAST(termination_date AS VARCHAR),
              current_compensation,
              employment_status = 'active',
              level_id,
              current_deferral_rate,
              CAST(employee_enrollment_date AS VARCHAR)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            ORDER BY employee_id
            """,
            [year],
        ).fetchall()
    if not rows:
        raise AssertionError(
            f"Simulated history has no workforce rows for {year}; the self-test "
            "cannot be built from an empty snapshot."
        )
    path = directory / f"census_{year}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CENSUS_COLUMNS)
        writer.writerows(rows)
    return path
