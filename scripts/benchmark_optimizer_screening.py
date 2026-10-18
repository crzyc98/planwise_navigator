#!/usr/bin/env python3
"""Run a bounded research benchmark; does not change production optimization."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import platform
from importlib.metadata import version
from pathlib import Path

import duckdb

from planalign_optimizer.baseline import load_baseline
from scripts.perf_profile.screening_benchmark import (
    BenchmarkSettings,
    ScreeningBenchmark,
    run_screening_benchmark,
)
from planalign_optimizer.spec_io import load_spec
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_pool import PoolEvent, resolve_worker_count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--census-csv", type=Path)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-simulations", required=True, type=int)
    parser.add_argument("--parallel", type=int)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def _progress(event: PoolEvent) -> None:
    print(
        f"{event.kind.value}: {event.job_name} ({event.duration_seconds})", flush=True
    )


def main() -> None:
    args = _parser().parse_args()
    spec = load_spec(args.spec)
    settings = BenchmarkSettings(
        candidate_count=args.candidates,
        repetitions=args.repetitions,
        max_simulations=args.max_simulations,
        search_seed=args.seed,
    )
    baseline = load_baseline(spec.baseline.config_path)
    if args.output.exists():
        raise ValueError("benchmark output directory must be fresh")
    if args.census_csv:
        # Conversion is outside timing and shared by all fidelities. Only use
        # synthetic fixtures for published evidence; never export census rows.
        census_path = args.output.parent / f"{args.output.name}-census.parquet"
        if census_path.exists():
            raise ValueError("converted census path must be fresh")
        census_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect() as connection:
            connection.read_csv(str(args.census_csv)).write_parquet(str(census_path))
        payload = baseline.model_dump(mode="python")
        payload["setup"]["census_parquet_path"] = str(census_path.resolve())
        baseline = SimulationConfig.model_validate(payload)
    budget = resolve_worker_count(args.parallel, settings.candidate_count)
    census = Path(baseline.model_dump(mode="python")["setup"]["census_parquet_path"])
    provenance = {
        "input_sha256": _file_hash(census),
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "tracked_changes": subprocess.run(["git", "diff", "--quiet"]).returncode != 0,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            name: version(name) for name in ("duckdb", "dbt-core", "dbt-duckdb")
        },
        "source_sha256": {
            str(path): _file_hash(path)
            for path in (
                Path(__file__).resolve(),
                *sorted(Path("planalign_optimizer").glob("*.py")),
                *sorted(Path("scripts/perf_profile").glob("screening*.py")),
            )
        },
    }
    report = run_screening_benchmark(
        spec, baseline, settings, args.output, budget, on_event=_progress
    )
    payload = report.model_dump(mode="json")
    payload["provenance"] = provenance
    (args.output / "benchmark.json").write_text(json.dumps(payload, indent=2) + "\n")
    (args.output / "report.md").write_text(render_report(report))
    print(f"{report.decision}: {args.output / 'report.md'}", flush=True)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_report(report: ScreeningBenchmark) -> str:
    lines = [
        "# Optimizer screening benchmark",
        "",
        f"Decision: **{report.decision}**",
        "",
        f"Worker limit: {report.worker_limit}; simulations: {report.simulation_count}",
        f"Prespecified minimum speedup: {report.settings.minimum_speedup:.2f}x",
        "",
        "| Trial | Full seconds | Screen seconds | Retained seconds | Retained | Speedup | Missed feasible | Frontier recall |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for index, trial in enumerate(report.trials):
        speedup = f"{trial.speedup:.2f}x" if trial.speedup is not None else "unknown"
        recall = trial.quality.frontier_retention
        lines.append(
            f"| {index + 1} | {trial.reference.wall_seconds:.2f} | "
            f"{trial.screening.wall_seconds:.2f} | {trial.validation.wall_seconds:.2f} | "
            f"{len(trial.selection)} | {speedup} | "
            f"{', '.join(trial.quality.missed_feasible) or 'none'} | {recall} |"
        )
    lines += [
        "",
        *[f"- {reason}" for reason in report.reasons],
        "",
        "Metrics use the latest year in each fidelity: first-year screening versus "
        "terminal-year full validation. Cost is terminal-year employer cost, not "
        "cumulative horizon cost. Every candidate retains the same simulation seed.",
        "",
        "Sampled aggregate process-tree peak RSS (MiB), reference/screen/retained:",
    ]
    lines += [
        f"- Trial {index + 1}: {trial.reference.sampled_peak_rss_mib:.1f} / "
        f"{trial.screening.sampled_peak_rss_mib:.1f} / "
        f"{trial.validation.sampled_peak_rss_mib:.1f}"
        for index, trial in enumerate(report.trials)
    ]
    lines += [
        "",
        "First-objective-only quality (same candidates/selection; no extra simulations):",
        *[
            f"- Trial {index + 1}: objective loss fraction "
            f"{trial.single_objective_quality.objective_loss_fraction}; "
            f"best-objective frontier recall {trial.single_objective_quality.frontier_retention}"
            for index, trial in enumerate(report.trials)
        ],
        "",
        "RSS is sampled every 100 ms, may double count shared pages, and can miss "
        "short peaks. This fixed-design experiment tests evaluation economics; "
        "it does not establish parity of an adaptive search or justify production rollout.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
