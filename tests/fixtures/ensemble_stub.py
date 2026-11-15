"""A stand-in for ``planalign simulate --seed-list`` in Studio ensemble tests.

Invoked as ``python ensemble_stub.py <behaviour> <output_root> <seeds> <job_id>``.
It speaks the real progress protocol and exits with the real CLI exit codes
(0 all seeds, 2 some failed, 3 none, 1 error), so the job runner is tested for
every outcome without simulating anything. ``<job_id>`` is only there so the
command line names the job, as the real one does through its paths.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import duckdb

from planalign_ensemble.progress import emit_pool_event
from planalign_orchestrator.run_pool import EventKind, PoolEvent


def _write_aggregate(output_root: Path, seeds: list[int]) -> None:
    database = output_root / "20260101T000000Z-scenario" / "ensemble.duckdb"
    database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            "CREATE TABLE fct_metric_distributions (ensemble_id VARCHAR, "
            "scenario_id VARCHAR, metric VARCHAR, simulation_year INTEGER, "
            "n_seeds INTEGER)"
        )
        conn.execute(
            "INSERT INTO fct_metric_distributions VALUES "
            "('ens-stub', 'scenario-in-db', 'active_headcount', 2026, ?)",
            [len(seeds)],
        )


def _run_seeds(seeds: list[int], fail: set[int]) -> None:
    for seed in seeds:
        emit_pool_event(PoolEvent(EventKind.JOB_STARTED, f"seed_{seed}"))
        kind = EventKind.JOB_FAILED if seed in fail else EventKind.JOB_COMPLETED
        error = f"seed {seed} broke" if seed in fail else None
        emit_pool_event(
            PoolEvent(kind, f"seed_{seed}", duration_seconds=0.1, error=error)
        )


_STUBBORN_CHILD = (
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "time.sleep(120)"
)


def _sleep_with_child(output_root: Path, seed: int) -> int:
    """Start a long seed with a grandchild in its own session that ignores
    SIGTERM (like a seed worker mid-dbt), then hang."""
    emit_pool_event(PoolEvent(EventKind.JOB_STARTED, f"seed_{seed}"))
    child = subprocess.Popen(
        [sys.executable, "-c", _STUBBORN_CHILD],
        start_new_session=True,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "child.pid").write_text(str(child.pid))
    time.sleep(120)
    return 0


def main(behaviour: str, output_root: str, raw_seeds: str) -> int:
    root = Path(output_root)
    seeds = [int(seed) for seed in raw_seeds.split(",")]
    if behaviour == "sleep":
        return _sleep_with_child(root, seeds[0])
    if behaviour == "crash":
        print(f"Simulation error: config broke under {root}", flush=True)
        return 1
    fail = {
        "success": set(),
        "partial": {seeds[-1]},
        "none": set(seeds),
    }[behaviour]
    _run_seeds(seeds, fail)
    if behaviour == "none":
        return 3
    _write_aggregate(root, seeds)
    return 2 if fail else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
