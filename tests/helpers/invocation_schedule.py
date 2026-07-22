"""Invocation-schedule reader/asserter (Feature 121).

Reads the ordered dbt command schedule a run recorded in ``run_execution_metadata``
(produced at the ``DbtRunner.execute_command`` seam by feature 120) and exposes the
invocation count plus the ordering invariants a consolidation must preserve.

Each recorded step is ``{seq, command, stage, year, runner_kind}`` (see
``planalign_orchestrator.construction.signature.ScheduleStep``); ``command`` is the
full dbt command string, so model presence/order is checked by substring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import duckdb


def read_latest_schedule(db_path: str | Path) -> Dict[str, object]:
    """Return {'invocation_count': int, 'steps': list[dict]} for the newest run."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT invocation_count, schedule_steps FROM run_execution_metadata "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise ValueError(f"No run_execution_metadata rows in {db_path}")
    count, steps_json = row
    steps = json.loads(steps_json) if steps_json else []
    return {"invocation_count": count, "steps": steps}


def _first_index(steps: List[dict], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in (step.get("command") or ""):
            return i
    return -1


def assert_invocation_count_at_most(db_path: str | Path, ceiling: int) -> int:
    """Assert the run's invocation_count is <= ceiling; return the actual count."""
    schedule = read_latest_schedule(db_path)
    count = schedule["invocation_count"]
    assert (
        count is not None and count <= ceiling
    ), f"invocation_count {count} exceeds ceiling {ceiling}"
    return count


def assert_accumulator_before_snapshot(steps: List[dict]) -> None:
    """Assert accumulator → events → snapshot relative order is preserved.

    (contracts/invocation-schedule.md invariant 2.)
    """
    events_idx = _first_index(steps, "fct_yearly_events")
    snapshot_idx = _first_index(steps, "fct_workforce_snapshot")
    assert events_idx != -1, "fct_yearly_events not found in schedule"
    assert snapshot_idx != -1, "fct_workforce_snapshot not found in schedule"
    assert events_idx < snapshot_idx, (
        "event build must precede snapshot build "
        f"(fct_yearly_events at {events_idx}, fct_workforce_snapshot at {snapshot_idx})"
    )
    for accumulator in (
        "int_enrollment_state_accumulator",
        "int_deferral_rate_state_accumulator",
    ):
        idx = _first_index(steps, accumulator)
        if idx != -1:
            assert (
                idx < snapshot_idx
            ), f"{accumulator} at {idx} must precede snapshot at {snapshot_idx}"
