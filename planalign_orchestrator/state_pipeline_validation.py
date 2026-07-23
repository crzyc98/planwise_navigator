"""Typed, PII-safe evidence contracts for the Feature 122 migration gates."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Sequence

import duckdb
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PHASE_ORDER = (
    "baseline_characterization",
    "run_database_isolation",
    "event_publication",
    "shadow_workforce/accumulator",
    "shadow_workforce/projection",
    "consumers_migrated/employer_eligibility",
    "consumers_migrated/employee_contributions",
    "consumers_migrated/employer_core",
    "consumers_migrated/employee_match",
    "consumers_migrated",
    "snapshot_composed_legacy_removed/composed",
    "snapshot_composed_legacy_removed/graph_contract",
    "snapshot_composed_legacy_removed",
    "state_stage_consolidated",
)
_UNSAFE_MARKERS = (
    "employee_row",
    "inv_emp_",
    "census.parquet",
    ".duckdb",
    "/private/",
    "/users/",
    "data/census",
)


def canonical_fingerprint(payload: Any) -> str:
    """Return SHA-256 over a stable JSON representation."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_fingerprint(path: Path) -> str | None:
    """Hash file bytes without reading or exposing their semantic contents."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_checked_value(value: Any) -> Any:
    serialized = json.dumps(value, sort_keys=True, default=str).lower()
    marker = next((item for item in _UNSAFE_MARKERS if item in serialized), None)
    if marker is not None:
        raise ValueError(
            f"checked evidence contains forbidden path/PII marker: {marker}"
        )
    return value


class ExclusionEntry(BaseModel):
    relation: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    column: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _reason_is_substantive(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("exclusion reason must not be blank")
        return value.strip()


class ExclusionManifest(BaseModel):
    schema_version: Literal[1] = 1
    exclusions: list[ExclusionEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _entries_are_unique(self) -> "ExclusionManifest":
        keys = [(entry.relation, entry.column) for entry in self.exclusions]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate relation-column exclusion")
        return self

    def validate_known_relations(self, known_relations: set[str]) -> None:
        unknown = sorted(
            {entry.relation for entry in self.exclusions} - known_relations
        )
        if unknown:
            raise ValueError(f"unknown relation exclusions: {', '.join(unknown)}")


def load_exclusion_manifest(
    path: Path, *, known_relations: set[str] | None = None
) -> ExclusionManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    manifest = ExclusionManifest.model_validate(payload)
    if known_relations is not None:
        manifest.validate_known_relations(known_relations)
    return manifest


class FileGuard(BaseModel):
    label: str = Field(min_length=1)
    exists: bool
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _fingerprint_matches_existence(self) -> "FileGuard":
        if self.exists != (self.sha256 is not None):
            raise ValueError("file guard existence and fingerprint disagree")
        return self

    @classmethod
    def capture(cls, label: str, path: Path) -> "FileGuard":
        fingerprint = file_fingerprint(path)
        return cls(label=label, exists=fingerprint is not None, sha256=fingerprint)


class CharacterizationRecord(BaseModel):
    schema_version: Literal[1] = 1
    baseline_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    code_fingerprint: str = Field(pattern=SHA256_PATTERN)
    normalized_config_fingerprint: str = Field(pattern=SHA256_PATTERN)
    census_fingerprint: str = Field(pattern=SHA256_PATTERN)
    seed_fingerprint: str = Field(pattern=SHA256_PATTERN)
    construction_fingerprint: str = Field(pattern=SHA256_PATTERN)
    database_fingerprint: str = Field(pattern=SHA256_PATTERN)
    horizon: tuple[int, int]
    census_rows: int = Field(gt=0)
    aggregate: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _record_is_safe_and_ordered(self) -> "CharacterizationRecord":
        if self.horizon[0] > self.horizon[1]:
            raise ValueError("horizon start must not exceed end")
        _validate_checked_value(self.aggregate)
        return self


class PhaseGateRecord(BaseModel):
    schema_version: Literal[1] = 1
    phase: str
    status: Literal["pending", "passed", "failed"]
    baseline_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    candidate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    artifact_labels: list[str] = Field(min_length=1)
    checks: dict[str, bool] = Field(default_factory=dict)
    file_guards: list[FileGuard] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _record_is_consistent_and_safe(self) -> "PhaseGateRecord":
        if self.phase not in PHASE_ORDER:
            raise ValueError(f"unknown phase: {self.phase}")
        _validate_checked_value(self.artifact_labels)
        _validate_checked_value(self.failures)
        if "employee_ssn" in json.dumps(self.artifact_labels).lower():
            raise ValueError("artifact labels cannot contain employee fields")
        if self.status == "passed" and (
            self.failures or any(not passed for passed in self.checks.values())
        ):
            raise ValueError("passed gate cannot contain failures")
        return self


def assert_phase_continuity(
    baseline: CharacterizationRecord,
    previous: Sequence[PhaseGateRecord],
    candidate: PhaseGateRecord,
) -> None:
    if candidate.baseline_id != baseline.baseline_id:
        raise ValueError("gate baseline_id does not match frozen characterization")
    for record in previous:
        if record.baseline_id != baseline.baseline_id:
            raise ValueError("previous gate baseline_id drifted")
        if record.status != "passed":
            raise ValueError("only passed gates can precede another gate")
    expected_index = len(previous)
    if (
        expected_index >= len(PHASE_ORDER)
        or candidate.phase != PHASE_ORDER[expected_index]
    ):
        expected = (
            PHASE_ORDER[expected_index] if expected_index < len(PHASE_ORDER) else "none"
        )
        raise ValueError(
            f"phase/checkpoint must be ordered; expected {expected}, got {candidate.phase}"
        )


def write_checked_json(path: Path, model: BaseModel) -> None:
    """Atomically serialize checked evidence after model validation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = model.model_dump_json(indent=2) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class CharacterizationVerification(BaseModel):
    passed: bool
    database_fingerprint: str
    aggregate: dict[str, Any]
    failures: list[str] = Field(default_factory=list)


def _scalar_int(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("aggregate query returned no row")
    return int(row[0])


def _database_aggregate(database: Path) -> dict[str, Any]:
    with duckdb.connect(str(database), read_only=True) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        ]
        row_counts = {
            table: _scalar_int(
                connection,
                f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34) * 2)}"',
            )
            for table in tables
            if table.startswith(("fct_", "dim_"))
        }
    return {"mart_row_counts": row_counts}


def verify_characterization_database(
    database: Path, characterization: CharacterizationRecord
) -> CharacterizationVerification:
    fingerprint = file_fingerprint(database)
    if fingerprint is None:
        raise FileNotFoundError(database)
    actual = _database_aggregate(database)
    failures: list[str] = []
    if fingerprint != characterization.database_fingerprint:
        failures.append("database fingerprint differs from frozen characterization")
    expected_rows = characterization.aggregate.get("mart_row_counts")
    if expected_rows is not None:
        actual_expected = {
            relation: actual["mart_row_counts"].get(relation)
            for relation in expected_rows
        }
        if actual_expected != expected_rows:
            failures.append("mart row counts differ from frozen characterization")
    return CharacterizationVerification(
        passed=not failures,
        database_fingerprint=fingerprint,
        aggregate=actual,
        failures=failures,
    )


def _tree_fingerprint(path: Path) -> str:
    payload = [
        {
            "path": item.relative_to(path).as_posix(),
            "sha256": file_fingerprint(item),
        }
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ]
    return canonical_fingerprint(payload)


def _relation_characterization(
    connection: duckdb.DuckDBPyConnection, relation: str
) -> dict[str, Any]:
    schema_rows = connection.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
        [relation],
    ).fetchall()
    if not schema_rows:
        return {"status": "not_built_in_either"}
    columns = [row[0] for row in schema_rows]
    projection = ", ".join(
        f'"{column.replace(chr(34), chr(34) * 2)}"' for column in columns
    )
    row_count = _scalar_int(connection, f'SELECT COUNT(*) FROM "{relation}"')
    distinct_count = _scalar_int(
        connection,
        f'SELECT COUNT(*) FROM (SELECT DISTINCT {projection} FROM "{relation}")',
    )
    duplicate_groups = _scalar_int(
        connection,
        f"SELECT COUNT(*) FROM (SELECT {projection}, COUNT(*) AS multiplicity "
        f'FROM "{relation}" GROUP BY {projection} HAVING COUNT(*) > 1)',
    )
    return {
        "status": "compared",
        "schema": [[row[0], row[1], row[2] == "YES"] for row in schema_rows],
        "row_count": row_count,
        "distinct_row_count": distinct_count,
        "duplicate_groups": duplicate_groups,
        "extra_duplicate_rows": row_count - distinct_count,
    }


def _event_count_aggregate(
    connection: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = 'fct_yearly_events'"
        ).fetchall()
    }
    required = {"scenario_id", "plan_design_id", "simulation_year", "event_type"}
    if not required.issubset(columns):
        return []
    rows = connection.execute(
        "SELECT scenario_id, plan_design_id, simulation_year, event_type, COUNT(*) "
        "FROM fct_yearly_events GROUP BY ALL "
        "ORDER BY scenario_id, plan_design_id, simulation_year, event_type"
    ).fetchall()
    return [
        {
            "scenario_id": row[0],
            "plan_design_id": row[1],
            "simulation_year": row[2],
            "event_type": row[3],
            "count": row[4],
        }
        for row in rows
    ]


def _transition_aggregate(
    connection: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = 'fct_workforce_snapshot'"
        ).fetchall()
    }
    required = {"employee_id", "simulation_year", "employment_status"}
    if not required.issubset(columns):
        return []
    scope = [
        column for column in ("scenario_id", "plan_design_id") if column in columns
    ]
    scope_projection = ", ".join(scope)
    prefix = f"{scope_projection}, " if scope_projection else ""
    partition = ", ".join([*scope, "employee_id"])
    group = ", ".join([*scope, "simulation_year", "prior_status", "employment_status"])
    rows = connection.execute(
        f"WITH transitions AS (SELECT {prefix}employee_id, simulation_year, employment_status, "
        f"LAG(employment_status) OVER (PARTITION BY {partition} ORDER BY simulation_year) AS prior_status "
        f"FROM fct_workforce_snapshot) SELECT {group}, COUNT(*) FROM transitions "
        f"GROUP BY {group} ORDER BY {group}"
    ).fetchall()
    keys = [*scope, "simulation_year", "prior_status", "current_status", "count"]
    return [dict(zip(keys, row)) for row in rows]


def capture_characterization(
    *,
    database: Path,
    config: Path,
    census: Path,
    seeds: Path,
    marts: Sequence[str],
    code_revision: str,
    baseline_id: str,
    horizon: tuple[int, int],
    census_rows: int,
) -> CharacterizationRecord:
    """Capture only aggregate baseline evidence from a completed isolated DB."""
    with duckdb.connect(str(database), read_only=True) as connection:
        mart_records = {
            relation: _relation_characterization(connection, relation)
            for relation in marts
        }
        metadata = connection.execute(
            "SELECT construction_signature_hash, config_fingerprint FROM run_metadata "
            "ORDER BY run_timestamp DESC LIMIT 1"
        ).fetchone()
        execution = connection.execute(
            "SELECT invocation_count, schedule_steps FROM run_execution_metadata "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
        construction = (
            metadata[0]
            if metadata and metadata[0]
            else canonical_fingerprint("unknown")
        )
        raw_schedule = json.loads(execution[1]) if execution and execution[1] else []
        schedule = [
            {
                "seq": step.get("seq"),
                "year": step.get("year"),
                "stage": step.get("stage"),
                "command_kind": str(step.get("command", "")).split(" ", 1)[0],
                "full_refresh": "--full-refresh" in str(step.get("command", "")),
                "command_fingerprint": canonical_fingerprint(step.get("command", "")),
            }
            for step in raw_schedule
        ]
        aggregate = {
            "marts": mart_records,
            "mart_row_counts": {
                name: record["row_count"]
                for name, record in mart_records.items()
                if record["status"] == "compared"
            },
            "event_counts": _event_count_aggregate(connection),
            "workforce_transition_counts": _transition_aggregate(connection),
            "invocation_count": execution[0] if execution else None,
            "schedule": schedule,
            "recorded_config_fingerprint": metadata[1] if metadata else None,
        }
    normalized_config = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    return CharacterizationRecord(
        baseline_id=baseline_id,
        code_fingerprint=canonical_fingerprint({"revision": code_revision}),
        normalized_config_fingerprint=canonical_fingerprint(normalized_config),
        census_fingerprint=file_fingerprint(census) or canonical_fingerprint("missing"),
        seed_fingerprint=_tree_fingerprint(seeds),
        construction_fingerprint=(
            construction
            if isinstance(construction, str) and len(construction) == 64
            else canonical_fingerprint(construction)
        ),
        database_fingerprint=file_fingerprint(database)
        or canonical_fingerprint("missing"),
        horizon=horizon,
        census_rows=census_rows,
        aggregate=aggregate,
    )
