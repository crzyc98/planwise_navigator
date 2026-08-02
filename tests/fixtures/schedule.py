"""Read finalized dbt command schedules from run execution metadata."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True)
class CommandRecord:
    simulation_year: int | None
    stage: str | None
    sequence: int
    verb: str
    selection: tuple[str, ...]
    full_refresh: bool
    extra_vars: dict[str, Any]


def _option_values(parts: list[str], option: str) -> tuple[str, ...]:
    if option not in parts:
        return ()
    start = parts.index(option) + 1
    values: list[str] = []
    for value in parts[start:]:
        if value.startswith("--"):
            break
        values.append(value)
    return tuple(values)


def _parse_step(step: dict[str, Any]) -> CommandRecord:
    parts = shlex.split(str(step.get("command", "")))
    return CommandRecord(
        simulation_year=step.get("year"),
        stage=step.get("stage"),
        sequence=int(step["seq"]),
        verb=parts[0] if parts else "",
        selection=_option_values(parts, "--select"),
        full_refresh="--full-refresh" in parts,
        extra_vars=dict(step.get("extra_vars") or {}),
    )


def read_command_schedule(database: Path) -> list[CommandRecord]:
    """Return the newest successfully finalized schedule in execution order."""
    with duckdb.connect(str(database), read_only=True) as connection:
        row = connection.execute(
            "SELECT schedule_steps FROM run_execution_metadata "
            "WHERE status = 'success' AND schedule_steps IS NOT NULL "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError(f"no finalized successful command schedule in {database}")
    steps = json.loads(row[0])
    return sorted((_parse_step(step) for step in steps), key=lambda item: item.sequence)
