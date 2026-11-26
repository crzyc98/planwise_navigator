#!/usr/bin/env python3
"""Check an acquisition and a minimum wage on one census (#1232).

Runs a baseline, the acquisition alone, the minimum wage alone and both
together, each as a full multi-year simulation in its own database, then
compares every run with the baseline that shares its config and seed. The
report holds aggregates only: counts, sums and differences, never a row.

    python3 scripts/dev.py -- python scripts/validate_acquisition_minimum_wage.py \
        --census path/to/census.parquet --config path/to/config.yaml \
        --minimum-wage 21 --out var/validate-1232/sponsor

The census needs an hourly rate column (``hourly_rate``, ``hours_worked`` or
``scheduled_hours_per_week``). Runs that already finished are reused, so an
interrupted command can be started again.
"""

from __future__ import annotations

import argparse
import copy
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Fixed before any run (#1232). None of them appears in the #1093 seed ledger.
SEEDS = (521, 523, 541)
VARIANTS = ("baseline", "acquisition", "minimum_wage", "both")
# A baseline on the same census with its hourly rate columns removed.
NO_RATES = "no_rate_columns"
RATE_COLUMNS = ("hourly_rate", "hours_worked", "scheduled_hours_per_week")


@dataclass(frozen=True)
class Plan:
    """What every run in one validation shares."""

    census: Path
    config: Path
    out: Path
    start_year: int
    end_year: int
    minimum_wage: float
    headcount: int

    @property
    def step_date(self) -> date:
        """The minimum wage takes effect mid-way through the second year."""
        return date(self.start_year + 1, 7, 1)

    def acquisitions(self) -> List[Dict[str, Any]]:
        """Three groups: before the step, on its date and after it is in force."""
        joins = {
            "early": date(self.start_year, 10, 1),
            "sameday": self.step_date,
            "late": date(self.start_year + 2, 4, 1),
        }
        groups: List[Dict[str, Any]] = [
            {"id": name, "headcount": self.headcount, "effective_date": day.isoformat()}
            for name, day in joins.items()
        ]
        # Paid 10% under the staff they are sampled from, who are already at
        # the minimum, so some of this group join below it.
        groups[-1]["relative_pay"] = 0.9
        return groups


@dataclass(frozen=True)
class Run:
    """One simulation: a config family, a variant and a seed."""

    family: str
    variant: str
    seed: int

    @property
    def name(self) -> str:
        return f"{self.family}-{self.variant}-{self.seed}"


_MATCH_TIER = {"employee_min": 0.0, "employee_max": 0.06}
# Each edge config changes one section of the config and leaves the rest alone.
EDGE_SETTINGS: Dict[str, Tuple[Tuple[str, ...], Dict[str, Any]]] = {
    # The cutoff too, or staff hired before it stay outside auto-enrollment.
    "ae_all_eligible": (
        ("enrollment", "auto_enrollment"),
        {
            "enabled": True,
            "scope": "all_eligible_employees",
            "hire_date_cutoff": "1900-01-01",
        },
    ),
    "points_core": (
        ("employer_core_contribution",),
        {
            "enabled": True,
            "status": "points_based",
            "points_schedule": [
                {"min_points": 0, "max_points": 40, "contribution_rate": 0.02},
                {"min_points": 40, "max_points": 60, "contribution_rate": 0.04},
                {"min_points": 60, "max_points": None, "contribution_rate": 0.06},
            ],
            "points_min_service_years": 2,
            "points_pre_service_rate": 1.0,
        },
    ),
    "tenure_match": (
        ("employer_match",),
        {
            "employer_match_status": "tenure_graded",
            "tenure_graded_bands": [
                {
                    "min_years": 0,
                    "max_years": 3,
                    "tiers": [{**_MATCH_TIER, "match_rate": 0.5}],
                },
                {
                    "min_years": 3,
                    "max_years": None,
                    "tiers": [{**_MATCH_TIER, "match_rate": 1.0}],
                },
            ],
        },
    ),
    "raise_budget": (("compensation",), {"raise_budget": 0.04}),
}
EDGE_CONFIGS = tuple(EDGE_SETTINGS)


def _apply_edge(raw: Dict[str, Any], family: str) -> None:
    """Apply one edge config's settings, if ``family`` is one."""
    if family not in EDGE_SETTINGS:
        return
    path, settings = EDGE_SETTINGS[family]
    section = raw
    for key in path:
        section = section.setdefault(key, {})
    section.update(copy.deepcopy(settings))


def build_config(plan: Plan, run: Run) -> Dict[str, Any]:
    """The base config with this run's years, seed, edge setting and changes."""
    raw: Dict[str, Any] = copy.deepcopy(yaml.safe_load(plan.config.read_text()))
    raw.setdefault("simulation", {}).update(
        {
            "start_year": plan.start_year,
            "end_year": plan.end_year,
            "random_seed": run.seed,
        }
    )
    raw.setdefault("setup", {})["census_parquet_path"] = str(plan.census)
    raw.setdefault("workforce", {})["acquisitions"] = []
    raw.setdefault("compensation", {})["minimum_wage"] = []
    _apply_edge(raw, run.family)
    if run.variant in ("acquisition", "both"):
        raw["workforce"]["acquisitions"] = plan.acquisitions()
    if run.variant in ("minimum_wage", "both"):
        raw["compensation"]["minimum_wage"] = [
            {
                "hourly_rate": plan.minimum_wage,
                "effective_date": plan.step_date.isoformat(),
            }
        ]
    return raw


def census_without_rates(plan: Plan, directory: Path) -> Path:
    """Copy the census without the columns that give an hourly rate."""
    import duckdb

    target = directory / "census_no_rates.parquet"
    with duckdb.connect() as connection:
        source = connection.read_parquet(str(plan.census))
        keep = [f'"{name}"' for name in source.columns if name not in RATE_COLUMNS]
        source.project(", ".join(keep)).write_parquet(str(target))
    return target


def run_directory(plan: Plan, run: Run) -> Path:
    return plan.out / "runs" / run.name


def simulate(directory: Path, start_year: int, end_year: int) -> None:
    """Worker: run one simulation into ``directory/sim.duckdb``."""
    database = directory / "sim.duckdb"
    os.environ["DATABASE_PATH"] = str(database)
    from planalign_orchestrator import ConstructionSpec, build_orchestrator
    from planalign_orchestrator.config import load_simulation_config

    config = load_simulation_config(directory / "config.yaml", env_overrides=False)
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=database,
            dbt_artifacts_dir=directory / "dbt",
            threads=1,
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=start_year, end_year=end_year)
    (directory / "done").write_text("ok\n")


def launch(plan: Plan, run: Run) -> str:
    """Run one simulation in its own process, unless it already finished."""
    directory = run_directory(plan, run)
    if (directory / "done").exists():
        return f"{run.name}: reused"
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("sim.duckdb*"):
        stale.unlink()
    config = build_config(plan, run)
    if run.family == NO_RATES:
        stripped = census_without_rates(plan, directory)
        config["setup"]["census_parquet_path"] = str(stripped)
    (directory / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    command = [sys.executable, __file__, "--worker", str(directory)]
    command += ["--start-year", str(plan.start_year), "--end-year", str(plan.end_year)]
    with (directory / "log.txt").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    return f"{run.name}: {'ok' if result.returncode == 0 else 'FAILED, see log.txt'}"


def planned_runs(seeds: List[int], edge: bool) -> List[Run]:
    """Every variant on each seed, then each edge config on the first seed."""
    runs = [Run("default", variant, seed) for seed in seeds for variant in VARIANTS]
    runs += [Run(NO_RATES, "baseline", seed) for seed in seeds]
    if edge:
        runs += [
            Run(family, variant, seeds[0])
            for family in EDGE_CONFIGS
            for variant in VARIANTS
        ]
    return runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--census", type=Path)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/simulation_config.yaml"
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument(
        "--minimum-wage", type=float, help="new minimum, dollars an hour"
    )
    parser.add_argument(
        "--headcount", type=int, default=100, help="people in each acquired group"
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    parser.add_argument("--jobs", type=int, default=3, help="simulations side by side")
    parser.add_argument("--no-edge", action="store_true", help="skip the edge configs")
    parser.add_argument(
        "--report-only", action="store_true", help="compare finished runs"
    )
    return parser.parse_args()


def make_plan(args: argparse.Namespace) -> Plan:
    missing = [n for n in ("census", "out", "minimum_wage") if getattr(args, n) is None]
    if missing:
        raise SystemExit(
            "missing: " + ", ".join("--" + n.replace("_", "-") for n in missing)
        )
    simulation = yaml.safe_load(args.config.read_text()).get("simulation", {})
    start_year = args.start_year or int(simulation["start_year"])
    end_year = args.end_year or start_year + 3
    if end_year < start_year + 2:
        raise SystemExit("the run needs at least three years")
    return Plan(
        census=args.census.resolve(),
        config=args.config.resolve(),
        out=args.out.resolve(),
        start_year=start_year,
        end_year=end_year,
        minimum_wage=args.minimum_wage,
        headcount=args.headcount,
    )


def main() -> int:
    args = parse_args()
    if args.worker:
        simulate(args.worker, args.start_year, args.end_year)
        return 0
    plan = make_plan(args)
    runs = planned_runs(args.seeds, edge=not args.no_edge)
    if not args.report_only:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for line in pool.map(lambda run: launch(plan, run), runs):
                print(line, flush=True)
    from validate_acquisition_minimum_wage_checks import write_report

    return write_report(plan, runs)


if __name__ == "__main__":
    raise SystemExit(main())
