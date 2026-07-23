"""Atomic latest-success selection for scenario-scoped managed runs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from planalign_core.constants import DATABASE_FILENAME

POINTER_FILENAME = "current_result.json"
RUN_METADATA_FILENAME = "run_metadata.json"


class CurrentResultIntegrityError(RuntimeError):
    """The persisted latest-success pointer or its target is inconsistent."""


def _canonical_uuid(value: str | uuid.UUID) -> uuid.UUID:
    try:
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("run_id must be a canonical UUID") from exc
    if isinstance(value, str) and str(parsed) != value:
        raise ValueError("run_id must be a canonical UUID")
    return parsed


class CurrentResultPointer(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    run_id: uuid.UUID
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    database_path: Path | None = Field(default=None, exclude=True)
    config_path: Path | None = Field(default=None, exclude=True)
    start_year: int | None = Field(default=None, exclude=True)
    end_year: int | None = Field(default=None, exclude=True)

    @field_validator("run_id", mode="before")
    @classmethod
    def _run_id_is_canonical(cls, value: object) -> uuid.UUID:
        return _canonical_uuid(value)  # type: ignore[arg-type]


class ResolvedScenarioReadContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_path: Path | None = None
    result_run_id: uuid.UUID | None = None
    active_run_id: uuid.UUID | None = None
    warning: Literal["run_in_progress"] | None = None
    config_path: Path | None = None
    start_year: int | None = None
    end_year: int | None = None


def _run_directory(scenario_path: Path, run_id: str | uuid.UUID) -> Path:
    canonical = _canonical_uuid(run_id)
    runs_root = (scenario_path / "runs").resolve()
    candidate = (runs_root / str(canonical)).resolve()
    if candidate.parent != runs_root:
        raise ValueError("run directory escapes scenario containment")
    return candidate


def allocate_run_directory(scenario_path: Path, run_id: str | uuid.UUID) -> Path:
    """Exclusively allocate one never-before-used managed-run directory."""
    run_dir = _run_directory(scenario_path, run_id)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(exist_ok=False)
    return run_dir


def _read_json(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurrentResultIntegrityError(f"invalid {label}") from exc
    if not isinstance(payload, dict):
        raise CurrentResultIntegrityError(f"invalid {label}")
    return payload


def _validate_target(
    scenario_path: Path, pointer: CurrentResultPointer
) -> CurrentResultPointer:
    run_dir = _run_directory(scenario_path, pointer.run_id)
    metadata_path = run_dir / RUN_METADATA_FILENAME
    metadata = _read_json(metadata_path, label="run metadata")
    if metadata.get("run_id") != str(pointer.run_id):
        raise CurrentResultIntegrityError(
            "run metadata identity does not match pointer"
        )
    if metadata.get("status") != "completed":
        raise CurrentResultIntegrityError("current result target is not completed")
    database_path = run_dir / DATABASE_FILENAME
    if not database_path.is_file():
        raise CurrentResultIntegrityError("current result database is missing")
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise CurrentResultIntegrityError(
            "current result database is not readable"
        ) from exc
    config_path = run_dir / "config.yaml"
    start_year = metadata.get("start_year")
    end_year = metadata.get("end_year")
    if config_path.is_file() and (start_year is None or end_year is None):
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            simulation = config.get("simulation", {})
            start_year = start_year or simulation.get("start_year")
            end_year = end_year or simulation.get("end_year")
        except (OSError, yaml.YAMLError) as exc:
            raise CurrentResultIntegrityError(
                "current result config is invalid"
            ) from exc
    return pointer.model_copy(
        update={
            "database_path": database_path,
            "config_path": config_path if config_path.is_file() else None,
            "start_year": int(start_year) if start_year is not None else None,
            "end_year": int(end_year) if end_year is not None else None,
        }
    )


def read_current_result(scenario_path: Path) -> CurrentResultPointer | None:
    """Read and validate the selected successful run, failing closed on corruption."""
    pointer_path = scenario_path / POINTER_FILENAME
    if not pointer_path.exists():
        return None
    try:
        pointer = CurrentResultPointer.model_validate(
            _read_json(pointer_path, label="current-result pointer")
        )
    except (ValueError, TypeError) as exc:
        raise CurrentResultIntegrityError("invalid current-result pointer") from exc
    return _validate_target(scenario_path, pointer)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_current_result(
    scenario_path: Path, run_id: str | uuid.UUID
) -> CurrentResultPointer:
    """Atomically promote a completed readable run as the latest successful result."""
    pointer = _validate_target(
        scenario_path, CurrentResultPointer(run_id=_canonical_uuid(run_id))
    )
    scenario_path.mkdir(parents=True, exist_ok=True)
    target = scenario_path / POINTER_FILENAME
    temporary = scenario_path / f".{POINTER_FILENAME}.{uuid.uuid4()}.tmp"
    serialized = pointer.model_dump_json(exclude_none=True, indent=2) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(scenario_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return pointer


def resolve_scenario_read_context(scenario_path: Path) -> ResolvedScenarioReadContext:
    pointer = read_current_result(scenario_path)
    scenario_data: dict = {}
    scenario_json = scenario_path / "scenario.json"
    if scenario_json.is_file():
        scenario_data = _read_json(scenario_json, label="scenario metadata")
    status = scenario_data.get("status")
    active_run_id: uuid.UUID | None = None
    if status in {"queued", "running"} and scenario_data.get("last_run_id"):
        try:
            active_run_id = _canonical_uuid(scenario_data["last_run_id"])
        except ValueError as exc:
            raise CurrentResultIntegrityError(
                "active attempt run ID is invalid"
            ) from exc
    return ResolvedScenarioReadContext(
        database_path=pointer.database_path if pointer else None,
        result_run_id=pointer.run_id if pointer else None,
        active_run_id=active_run_id,
        warning="run_in_progress" if active_run_id else None,
        config_path=pointer.config_path if pointer else None,
        start_year=pointer.start_year if pointer else None,
        end_year=pointer.end_year if pointer else None,
    )
