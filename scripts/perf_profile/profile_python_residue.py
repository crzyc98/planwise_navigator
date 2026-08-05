"""Attribute the orchestrator-Python residue to specific subsystems (#521).

The run-cost profile (#455/#478/#519) decomposes total wall time into
``computation`` (dbt model execute), ``overhead`` (per-invocation dbt
tooling), and ``residue`` (orchestrator Python outside any dbt subprocess
call) — but residue has only ever been reported as a leftover, never
measured directly. This script measures it in three isolated reps against
the same reference config + workspace census used by
``docs/perf/run_cost_profile_production.md``:

1. **rep 1 — baseline (monitors on)** — ``InvocationRecorder`` only (no
   profiler), giving ``residue_s = total_wall_s - sum(invocation wall_s)``
   exactly like the accepted reports. Also directly times (plain
   ``perf_counter``, no cProfile) the four background resource-monitor
   threads' create/join lifecycle cost, since that turns out to be roughly
   half of the residue on its own.
2. **rep 2 — baseline, monitors suppressed** — identical, except the four
   monitor components' thread-spawning methods are patched to no-ops for
   this rep only. Gives a clean "everything else" residue number with no
   profiler involved, so it cannot itself be a cProfile artifact.
3. **rep 3 — profiled, monitors suppressed** — a single ``cProfile.Profile``
   enabled for the whole run, disabled around every
   ``DbtRunner.execute_command`` call so dbt subprocess wall time (and the
   Python inside ``execute_command`` itself, already counted in "overhead")
   is excluded. Monitors are suppressed here too: a single shared
   ``cProfile.Profile`` cannot correctly separate call stacks across
   concurrently running OS threads, and in practice this corrupted
   attribution until suppression was added.

Each profiled function's ``tottime`` is bucketed by source file into the
candidates named in #521 (StateManager, DataValidator, HazardCacheManager,
RegistryManager/hooks, run_metadata/config-fingerprint, other orchestrator
Python, non-orchestrator runtime). Bucket shares from rep 3 are scaled onto
rep 2's clean residue_s — apples to apples, since both are
monitor-suppressed — rather than rep 1's raw residue, so the reported
seconds are not inflated by cProfile's own instrumentation overhead.

No production code is modified — the invocation timer, the monitor-thread
patches, and the profiler bracket all attach to one live instance/class for
the duration of a single rep, restored immediately after, the same
non-invasive technique ``dbt_timing.InvocationRecorder`` already uses.

Usage:
    python -m scripts.perf_profile.profile_python_residue \\
        --campaign-id residue-521 --horizon 2025-2029
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .profile_config import OUTPUT_DIR, ROOT
from .run_matrix import (
    _build_wrapper_orchestrator,
    _write_effective_config,
    database_environment,
)
from .dbt_timing import InvocationRecorder, attach_stage_tracking

CONFIG_YAML = ROOT / "config" / "simulation_config.yaml"
DEFAULT_CENSUS = (
    ROOT
    / "workspaces"
    / "1497b19c-b212-4c67-82d3-bc0455b637e0"
    / "data"
    / "census.parquet"
)

# PerformanceMonitor.time_operation() and AdaptiveMemoryManager both spawn a
# daemon thread that polls psutil in a time.sleep() loop for the lifetime of
# the operation/run they wrap — including the dbt subprocess calls nested
# inside that operation. Whatever CPython mechanism lets cProfile see a frame
# from these threads, they run *concurrently* with (not sequentially before
# or after) both dbt calls and other orchestrator Python; their tottime does
# not represent addressable sequential residue and would badly overstate it
# if left in the denominator. Bucketed separately and excluded from the
# share calculation, not silently dropped.
BACKGROUND_MONITOR_MARKERS = (
    "planalign_orchestrator/monitoring/base.py",
    "planalign_orchestrator/adaptive_memory_manager.py",
)


def _is_background_monitor_frame(filename: str, funcname: str) -> bool:
    if any(marker in filename for marker in BACKGROUND_MONITOR_MARKERS):
        return True
    # The daemon Thread's own bootstrap/run frames and the time.sleep() call
    # inside its poll loop — indistinguishable by filename alone since they
    # live in stdlib threading.py / built-ins shared with legitimate callers,
    # so they are only swept in via function name.
    if filename.endswith("threading.py") and funcname in {
        "run",
        "_bootstrap",
        "_bootstrap_inner",
    }:
        return True
    return False


BACKGROUND_MONITOR_BUCKET = "background monitor threads (excluded — concurrent with dbt, not sequential residue)"

# Longest/most specific path fragment first — matched by substring against
# each profiled frame's filename.
BUCKET_PATTERNS: List[tuple[str, str]] = [
    (
        "planalign_orchestrator/utils.py",
        "DatabaseConnectionManager (connect/retry/transaction)",
    ),
    ("planalign_orchestrator/pipeline/state_manager.py", "StateManager (cleanup/DDL)"),
    ("planalign_orchestrator/validation.py", "DataValidator (validate_year_results)"),
    ("planalign_orchestrator/pipeline/stage_validator.py", "StageValidator"),
    ("planalign_orchestrator/hazard_cache_manager.py", "HazardCacheManager"),
    ("planalign_orchestrator/registries.py", "RegistryManager"),
    ("planalign_orchestrator/pipeline/hooks.py", "HookManager/hook dispatch"),
    ("planalign_orchestrator/run_metadata.py", "run_metadata writes"),
    ("planalign_orchestrator/run_summary.py", "run_summary/reporting"),
    ("planalign_orchestrator/config/export.py", "config export/fingerprint"),
    ("planalign_orchestrator/change_validation.py", "change_validation"),
    (
        "planalign_orchestrator/state_pipeline_validation.py",
        "state_pipeline_validation",
    ),
    ("planalign_orchestrator/workforce_projection", "WorkforceProjection rebuild"),
    ("planalign_orchestrator/enrollment_projection", "EnrollmentProjection rebuild"),
    ("planalign_orchestrator/pipeline/year_executor.py", "YearExecutor"),
    (
        "planalign_orchestrator/pipeline/event_generation_executor.py",
        "EventGenerationExecutor",
    ),
    ("planalign_orchestrator/pipeline_orchestrator.py", "PipelineOrchestrator glue"),
    ("planalign_orchestrator/dbt_runner.py", "DbtRunner (non-subprocess Python)"),
    ("planalign_orchestrator/", "other orchestrator Python"),
]


def _bucket_for(filename: str) -> str:
    for fragment, label in BUCKET_PATTERNS:
        if fragment in filename:
            return label
    if "duckdb" in filename:
        return "duckdb Python client"
    if (
        filename.startswith("<")
        or "/lib/python" in filename
        or "site-packages" in filename
    ):
        return "stdlib/third-party runtime"
    return "other"


@dataclass
class RepResult:
    total_wall_s: float
    invocation_wall_s: float
    residue_s: float
    monitor_start_s: float
    monitor_stop_s: float


@contextmanager
def _timed_monitor_lifecycle():
    """Time real main-thread wall-clock spent creating/tearing down the four
    background monitor threads — without suppressing them. Used in the
    baseline (unprofiled) rep, where a plain ``time.perf_counter()`` wrapper
    is not subject to cProfile's multi-thread attribution problems, so this
    number is trustworthy at face value rather than share-scaled.

    ``_stop_monitoring``/``stop_monitoring`` call ``Thread.join(timeout=...)``
    — a real blocking wait on the main thread for the daemon thread to notice
    its stop flag, capped at 1.0s (PerformanceMonitor) or 2x the polling
    interval (AdaptiveMemoryManager/CPUMonitor/MemoryMonitor). This runs once
    per instrumented "operation" (multi_year_run, year_simulation_N,
    stage_X_N, ...) — on the order of 25+ times across a 5-year run.
    """
    from planalign_orchestrator.monitoring.base import PerformanceMonitor
    from planalign_orchestrator.adaptive_memory_manager import AdaptiveMemoryManager
    from planalign_orchestrator.resources.cpu_monitor import CPUMonitor
    from planalign_orchestrator.resources.memory_monitor import MemoryMonitor

    totals = {"start": 0.0, "stop": 0.0}
    originals: List[tuple] = []

    def _wrap(cls, name: str, key: str) -> None:
        original = getattr(cls, name)
        originals.append((cls, name, original))

        def wrapper(self, *args, **kwargs):
            t0 = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                totals[key] += time.perf_counter() - t0

        setattr(cls, name, wrapper)

    for cls, start_name, stop_name in [
        (PerformanceMonitor, "_start_monitoring", "_stop_monitoring"),
        (AdaptiveMemoryManager, "start_monitoring", "stop_monitoring"),
        (CPUMonitor, "start_monitoring", "stop_monitoring"),
        (MemoryMonitor, "start_monitoring", "stop_monitoring"),
    ]:
        _wrap(cls, start_name, "start")
        _wrap(cls, stop_name, "stop")

    try:
        yield totals
    finally:
        for cls, name, original in originals:
            setattr(cls, name, original)


def _run_baseline(
    effective_config: Path,
    db_path: Path,
    horizon: tuple[int, int],
    *,
    suppress_monitors: bool = False,
) -> RepResult:
    """InvocationRecorder only (no profiler) — a clean, unprofiled residue number.

    With ``suppress_monitors=False`` (rep 1) this is the real production
    residue, decomposed further by ``_timed_monitor_lifecycle`` into monitor
    thread create/join overhead vs. everything else. With
    ``suppress_monitors=True`` (rep 2) the four background monitor threads
    never start, giving a clean "everything else" residue number — measured
    by a plain wall clock, not cProfile — to scale the rep-3 cProfile bucket
    shares onto (apples to apples: both are monitor-suppressed).
    """
    monitor_ctx = (
        _suppressed_background_monitors()
        if suppress_monitors
        else _timed_monitor_lifecycle()
    )
    with database_environment(db_path), monitor_ctx as monitor_result:
        orchestrator = _build_wrapper_orchestrator(effective_config, db_path, None)
        recorder = InvocationRecorder(orchestrator.dbt_runner)
        attach_stage_tracking(orchestrator, recorder)
        start = time.perf_counter()
        orchestrator.execute_multi_year_simulation(
            start_year=horizon[0], end_year=horizon[1]
        )
        total_wall = time.perf_counter() - start
        recorder.unwrap()
    invocation_wall = sum(inv.wall_s for inv in recorder.invocations)
    monitor_totals = (
        monitor_result if not suppress_monitors else {"start": 0.0, "stop": 0.0}
    )
    return RepResult(
        total_wall_s=total_wall,
        invocation_wall_s=invocation_wall,
        residue_s=total_wall - invocation_wall,
        monitor_start_s=monitor_totals["start"],
        monitor_stop_s=monitor_totals["stop"],
    )


@contextmanager
def _suppressed_background_monitors():
    """Disable every psutil-polling daemon thread for the profiled rep only.

    Four separate components each spawn a background ``Thread`` that polls
    in a ``time.sleep()`` loop for the lifetime of the operation/run they
    wrap: ``PerformanceMonitor.time_operation()``, ``AdaptiveMemoryManager``,
    and (when the resource-managed stage path is active) ``ResourceManager``'s
    ``CPUMonitor`` and ``MemoryMonitor``. A single shared ``cProfile.Profile``
    cannot correctly separate call stacks across concurrently running OS
    threads; in practice this corrupts caller/callee attribution (frames show
    implausible callers like ``builtins.next``, and total call counts stop
    reconciling with the sum over recorded callers). Suppressing thread
    creation here — for this measurement rep only, restored immediately after
    — removes that source of corruption so the profiled rep reflects only the
    orchestrator's own sequential Python. The baseline rep (no profiler)
    still measures the real, uncorrupted wall-clock residue including
    whatever thread start/join overhead genuinely costs; this context only
    changes which rep the bucket *shares* are computed from.
    """
    from planalign_orchestrator.monitoring.base import PerformanceMonitor
    from planalign_orchestrator.adaptive_memory_manager import AdaptiveMemoryManager
    from planalign_orchestrator.resources.cpu_monitor import CPUMonitor
    from planalign_orchestrator.resources.memory_monitor import MemoryMonitor

    patches = [
        (PerformanceMonitor, "_start_monitoring", lambda self, metrics: None),
        (AdaptiveMemoryManager, "start_monitoring", lambda self: None),
        (CPUMonitor, "start_monitoring", lambda self: None),
        (MemoryMonitor, "start_monitoring", lambda self: None),
    ]
    originals = [(cls, name, getattr(cls, name)) for cls, name, _ in patches]
    for cls, name, replacement in patches:
        setattr(cls, name, replacement)
    try:
        yield
    finally:
        for cls, name, original in originals:
            setattr(cls, name, original)


def _run_profiled(
    effective_config: Path, db_path: Path, horizon: tuple[int, int]
) -> pstats.Stats:
    """Rep 2: cProfile bracketed to exclude every dbt subprocess call."""
    profiler = cProfile.Profile()

    with database_environment(db_path), _suppressed_background_monitors():
        orchestrator = _build_wrapper_orchestrator(effective_config, db_path, None)
        runner = orchestrator.dbt_runner
        original_execute = runner.execute_command

        def _bracketed_execute(command_args, **kwargs):
            profiler.disable()
            try:
                return original_execute(command_args, **kwargs)
            finally:
                profiler.enable()

        runner.execute_command = _bracketed_execute
        try:
            profiler.enable()
            orchestrator.execute_multi_year_simulation(
                start_year=horizon[0], end_year=horizon[1]
            )
        finally:
            profiler.disable()
            runner.execute_command = original_execute

    return pstats.Stats(profiler)


# Shared with any ordinary caller, so it can't be bucketed by its own
# (filename, func) key — attribute proportionally via its callers instead.
# pstats reports built-ins as "<built-in method time.sleep>", not "sleep".
_AMBIGUOUS_BUILTINS = {"<built-in method time.sleep>"}


def _split_by_caller(callers: dict) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for (c_file, _c_line, c_func), value in callers.items():
        cumtime = value[3] if len(value) >= 4 else value[-1]
        bucket = (
            BACKGROUND_MONITOR_BUCKET
            if _is_background_monitor_frame(c_file, c_func)
            else _bucket_for(c_file)
        )
        result[bucket] = result.get(bucket, 0.0) + cumtime
    return result


def _bucket_breakdown(stats: pstats.Stats) -> Dict[str, float]:
    buckets: Dict[str, float] = {}
    for (filename, _line, funcname), (_cc, _nc, tottime, _ct, callers) in stats.stats.items():  # type: ignore[attr-defined]
        if _is_background_monitor_frame(filename, funcname):
            buckets[BACKGROUND_MONITOR_BUCKET] = (
                buckets.get(BACKGROUND_MONITOR_BUCKET, 0.0) + tottime
            )
            continue
        if funcname in _AMBIGUOUS_BUILTINS and callers:
            for bucket, amount in _split_by_caller(callers).items():
                buckets[bucket] = buckets.get(bucket, 0.0) + amount
            continue
        bucket = _bucket_for(filename)
        buckets[bucket] = buckets.get(bucket, 0.0) + tottime
    return buckets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="residue-521")
    parser.add_argument("--config", type=Path, default=CONFIG_YAML)
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--horizon", default="2025-2029")
    args = parser.parse_args()

    start_year, end_year = (int(x) for x in args.horizon.split("-"))
    horizon = (start_year, end_year)

    campaign_root = OUTPUT_DIR / args.campaign_id
    (campaign_root / "db").mkdir(parents=True, exist_ok=True)
    (campaign_root / "configs").mkdir(parents=True, exist_ok=True)

    effective_config = _write_effective_config(
        args.config, args.census, horizon, campaign_root / "configs" / "effective.yaml"
    )

    print("=== Rep 1/3: baseline (InvocationRecorder only, monitors on) ===")
    baseline_db = campaign_root / "db" / "baseline.duckdb"
    if baseline_db.exists():
        baseline_db.unlink()
    baseline = _run_baseline(effective_config, baseline_db, horizon)
    print(
        f"total_wall_s={baseline.total_wall_s:.2f} "
        f"invocation_wall_s={baseline.invocation_wall_s:.2f} "
        f"residue_s={baseline.residue_s:.2f} "
        f"({baseline.residue_s / baseline.total_wall_s:.1%})"
    )
    monitor_lifecycle_s = baseline.monitor_start_s + baseline.monitor_stop_s
    print(
        f"  of which, monitor thread lifecycle (directly timed, not cProfile-scaled): "
        f"start={baseline.monitor_start_s:.2f}s stop/join={baseline.monitor_stop_s:.2f}s "
        f"total={monitor_lifecycle_s:.2f}s ({monitor_lifecycle_s / baseline.residue_s:.1%} of residue)"
    )

    print(
        "\n=== Rep 2/3: baseline, monitors suppressed (clean 'everything else' residue) ==="
    )
    suppressed_db = campaign_root / "db" / "baseline_suppressed.duckdb"
    if suppressed_db.exists():
        suppressed_db.unlink()
    suppressed = _run_baseline(
        effective_config, suppressed_db, horizon, suppress_monitors=True
    )
    print(
        f"total_wall_s={suppressed.total_wall_s:.2f} "
        f"invocation_wall_s={suppressed.invocation_wall_s:.2f} "
        f"residue_s={suppressed.residue_s:.2f}"
    )
    print(
        f"  reconciliation: rep1 residue ({baseline.residue_s:.2f}s) - monitor lifecycle "
        f"({monitor_lifecycle_s:.2f}s) = {baseline.residue_s - monitor_lifecycle_s:.2f}s, "
        f"vs. rep 2's directly measured {suppressed.residue_s:.2f}s"
    )

    print(
        "\n=== Rep 3/3: profiled (cProfile bracketed around dbt calls, monitors suppressed) ==="
    )
    profiled_db = campaign_root / "db" / "profiled.duckdb"
    if profiled_db.exists():
        profiled_db.unlink()
    stats = _run_profiled(effective_config, profiled_db, horizon)
    stats.dump_stats(str(campaign_root / "profiled.prof"))

    buckets = _bucket_breakdown(stats)
    background = buckets.pop(BACKGROUND_MONITOR_BUCKET, 0.0)
    total_profiled = sum(buckets.values())
    print(
        f"total profiled tottime, sequential only (cProfile-inflated): "
        f"{total_profiled:.2f}s  [{BACKGROUND_MONITOR_BUCKET}: {background:.2f}s, excluded from shares]\n"
    )

    print(f"{'Bucket':<55} {'tottime':>10} {'share':>8} {'est. residue_s':>15}")
    for label, tottime in sorted(buckets.items(), key=lambda kv: -kv[1]):
        share = tottime / total_profiled if total_profiled else 0.0
        est_seconds = share * suppressed.residue_s
        print(f"{label:<55} {tottime:>10.3f} {share:>8.1%} {est_seconds:>15.2f}")

    unattributed = suppressed.residue_s - total_profiled
    print(
        f"\nRep 2 residue_s (scaled onto, monitors-suppressed, apples-to-apples with rep 3): "
        f"{suppressed.residue_s:.2f}s"
    )
    print(
        f"cProfile only captured {total_profiled:.2f}s of that as traceable Python "
        f"bytecode; the remaining {unattributed:.2f}s is time the main thread spent "
        f"blocked in C-level calls (DB connect/lock-wait, OS scheduling) that cProfile "
        f"cannot attribute to a Python frame."
    )
    print(f"Artifacts: {campaign_root}")


if __name__ == "__main__":
    main()
