"""Matched actual-CLI A/B campaign; fresh dbt projects and databases per run.

Usage: python -m scripts.perf_profile.hash_ab --help
Timing includes Typer simulate and its children, excluding interpreter startup.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Iterator

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.change_validation import compare_marts_detailed
from planalign_orchestrator.state_pipeline_validation import load_exclusion_manifest
from .dbt_timing import InvocationRecorder
from .profile_config import fingerprint_file, fingerprint_seed_tree
from .run_matrix import _PeakRssMonitor, _cpu_delta, database_environment

ROOT = Path(__file__).resolve().parents[2]
COPY_IGNORE = shutil.ignore_patterns(
    "target", "logs", "*.duckdb", "*.duckdb.wal", ".user.yml"
)


def project_fingerprints(project: Path) -> dict[str, str | None]:
    """Fingerprint source/dependencies, excluding mutable dbt runtime artifacts."""
    return {
        str(path.relative_to(project)): fingerprint_file(path)
        for path in sorted(project.rglob("*"))
        if path.is_file()
        and not any(
            part in {"target", "logs", "__pycache__"}
            for part in path.relative_to(project).parts
        )
        and not path.name.endswith((".duckdb", ".duckdb.wal"))
        and path.name != ".user.yml"
    }


@contextmanager
def record_invocations() -> Iterator[list[InvocationRecorder]]:
    """Capture every CLI-created runner without changing product construction."""
    original = DbtRunner.execute_command
    recorders: list[InvocationRecorder] = []

    def execute(runner: DbtRunner, command_args: list[str], **kwargs: Any) -> Any:
        runner.execute_command = original.__get__(runner, DbtRunner)
        recorder = InvocationRecorder(runner)
        recorders.append(recorder)
        return runner.execute_command(command_args, **kwargs)

    DbtRunner.execute_command = execute
    try:
        yield recorders
    finally:
        DbtRunner.execute_command = original
        for recorder in recorders:
            recorder.unwrap()


def _invoke_cli(database: Path, project: Path, config: Path, horizon: str) -> None:
    from planalign_cli.main import app

    result = app(
        args=[
            "simulate",
            horizon,
            "--config",
            str(config),
            "--database",
            str(database),
            "--dbt-project-dir",
            str(project),
            "--threads",
            "1",
            "--fail-on-validation-error",
        ],
        standalone_mode=False,
    )
    if result not in (None, 0):
        raise RuntimeError(f"CLI exit code {result}")


def measure(directory: Path, project: Path, config: Path, horizon: str) -> dict:
    """Run one actual CLI command and retain evidence even when it fails."""
    directory.mkdir(exist_ok=False)
    database = directory / "simulation.duckdb"
    isolated_project = directory / "dbt"
    shutil.copytree(project, isolated_project, ignore=COPY_IGNORE)
    memory = _PeakRssMonitor()
    error = None
    with record_invocations() as recorders, database_environment(database):
        memory.start()
        cpu = os.times()
        started = time.perf_counter()
        try:
            with (
                (directory / "run.log").open("w") as log,
                redirect_stdout(log),
                redirect_stderr(log),
            ):
                _invoke_cli(database, isolated_project, config, horizon)
        except (Exception, SystemExit) as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            wall = time.perf_counter() - started
            cpu_s = _cpu_delta(cpu, os.times())
            rss = memory.stop()
    invocations = [
        item.model_dump() for recorder in recorders for item in recorder.invocations
    ]
    sample = {
        "wall_s": wall,
        "cpu_s": cpu_s,
        "peak_rss_mib": rss,
        "error": error,
        "database": str(database),
        "invocations": invocations,
    }
    (directory / "measurement.json").write_text(json.dumps(sample, indent=2))
    if error is not None:
        raise RuntimeError(
            f"Failed sample {directory.name}; see measurement.json and run.log"
        )
    return sample


def environment() -> dict:
    import duckdb

    child = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import duckdb; print(duckdb.__version__, duckdb.__file__)",
        ],
        text=True,
    ).strip()
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("duckdb", "dbt-core", "dbt-duckdb", "pydantic")
        },
        "duckdb_module": duckdb.__file__,
        "child_duckdb": child,
        "pythonpath": os.environ.get("PYTHONPATH"),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }


def prepare(args: argparse.Namespace) -> dict:
    baseline = project_fingerprints(args.baseline_project)
    candidate = project_fingerprints(args.candidate_project)
    differences = [
        name
        for name in baseline.keys() | candidate.keys()
        if baseline.get(name) != candidate.get(name)
    ]
    if differences != ["macros/utils/stable_hash.sql"]:
        raise ValueError(
            f"Projects must differ only in stable_hash.sql; found {differences}"
        )
    if not args.census.is_file():
        raise FileNotFoundError(args.census)
    args.output.mkdir(exist_ok=False, parents=True)
    start, end = map(int, args.horizon.split("-"))
    config = load_simulation_config(args.config, env_overrides=False)
    config.setup["census_parquet_path"] = str(args.census)
    config.simulation.start_year, config.simulation.end_year = start, end
    config.simulation.random_seed = args.seed
    effective = args.output / "config.json"
    effective.write_text(config.model_dump_json(indent=2))
    return {
        "environment": environment(),
        "config_sha256": fingerprint_file(effective),
        "census_sha256": fingerprint_file(args.census),
        "seeds_sha256": fingerprint_seed_tree(args.baseline_project / "seeds"),
        "projects": {"baseline": baseline, "candidate": candidate},
        "timing_boundary": "in-process actual Typer simulate, including health/validation and child processes",
        "samples": [],
    }


def _run_samples(args: argparse.Namespace, payload: dict, campaign: Path) -> None:
    projects = {"baseline": args.baseline_project, "candidate": args.candidate_project}
    for repetition in range(args.pairs + 1):
        order = (
            ("baseline", "candidate")
            if repetition <= 1 or repetition % 2
            else ("candidate", "baseline")
        )
        for arm in order:
            name = f"{'warmup' if repetition == 0 else f'pair_{repetition}'}_{arm}"
            print(f"Starting {name}", flush=True)
            sample = measure(
                args.output / name,
                projects[arm],
                args.output / "config.json",
                args.horizon,
            )
            payload["samples"].append(
                {"arm": arm, "scored": repetition > 0, "name": name, **sample}
            )
            campaign.write_text(json.dumps(payload, indent=2))
            print(f"Completed {name}: {sample['wall_s']:.2f}s", flush=True)


def run_campaign(args: argparse.Namespace) -> None:
    payload = prepare(args)
    shared = ROOT / "dbt/simulation.duckdb"
    payload["shared_before"] = fingerprint_file(shared)
    campaign = args.output / "campaign.json"
    try:
        _run_samples(args, payload, campaign)
        medians = {
            arm: statistics.median(
                s["wall_s"]
                for s in payload["samples"]
                if s["arm"] == arm and s["scored"]
            )
            for arm in ("baseline", "candidate")
        }
        payload["median_wall_s"] = medians
        payload["wall_improvement_fraction"] = (
            1 - medians["candidate"] / medians["baseline"]
        )
        payload["performance_gate_passed"] = (
            payload["wall_improvement_fraction"] >= 0.20
        )
        payload["parity"] = compare_campaign(args.output, payload["samples"])
        if not payload["parity"]["passed"]:
            raise RuntimeError("Full-run parity or determinism failed")
    finally:
        payload["shared_after"] = fingerprint_file(shared)
        payload["shared_unchanged"] = (
            payload["shared_before"] == payload["shared_after"]
        )
        campaign.write_text(json.dumps(payload, indent=2))
        if not payload["shared_unchanged"]:
            raise RuntimeError("Shared database changed during campaign")


def compare_campaign(output: Path, samples: list[dict]) -> dict:
    scored = [sample for sample in samples if sample["scored"]]
    baseline = next(sample for sample in scored if sample["arm"] == "baseline")
    manifest = json.loads(
        (output / baseline["name"] / "dbt/target/manifest.json").read_text()
    )
    marts = sorted(
        {
            node["name"]
            for node in manifest["nodes"].values()
            if node["resource_type"] == "model"
            and node["original_file_path"].startswith("models/marts/")
            and node["name"].startswith(("fct_", "dim_"))
        }
    )
    exclusions = load_exclusion_manifest(
        ROOT / "specs/122-state-pipeline-redesign/contracts/parity-exclusions.yaml"
    ).exclusions
    comparisons = {}
    for sample in scored:
        if sample is baseline:
            continue
        results = compare_marts_detailed(
            baseline["database"], sample["database"], marts, exclusions
        )
        comparisons[sample["name"]] = {
            name: asdict(result) for name, result in results.items()
        }
    passed = bool(comparisons) and all(
        all(
            result["status"] in {"compared", "not_built_in_either"}
            for result in results.values()
        )
        and any(result["status"] == "compared" for result in results.values())
        for results in comparisons.values()
    )
    return {
        "passed": passed,
        "comparisons": comparisons,
        "exclusions": [entry.model_dump() for entry in exclusions],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "config",
        "census",
        "baseline-project",
        "candidate-project",
        "output",
    ):
        parser.add_argument(
            f"--{option}", required=True, type=lambda value: Path(value).resolve()
        )
    parser.add_argument("--horizon", default="2025-2029")
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--pairs", default=3, type=int)
    args = parser.parse_args()
    if args.pairs < 3:
        parser.error("At least three scored pairs are required")
    run_campaign(args)


if __name__ == "__main__":
    main()
