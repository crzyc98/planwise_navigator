"""Construction provenance schema-evolution and lifecycle contracts."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import (
    ConstructionSignature,
    WorkSchedule,
)
from planalign_orchestrator.run_metadata import (
    RunMetadataError,
    append_execution_record,
    check_and_record_run,
)
from planalign_orchestrator.utils import DatabaseConnectionManager

LEGACY_RUN_ID = "00000000-0000-4000-8000-000000000119"


def _signature(database: Path) -> ConstructionSignature:
    return ConstructionSignature(
        entry_point="cli.simulate",
        runner_kind="dbt",
        database_path=str(database),
        dbt_project_dir=None,
        thread_count=1,
        initialization_policy="none",
        installed_hook_names=(),
        execution_engine="dbt",
    )


def _create_old_schema(database: Path) -> None:
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            """
            CREATE TABLE run_metadata (
                run_id VARCHAR NOT NULL,
                run_timestamp TIMESTAMP NOT NULL,
                run_type VARCHAR NOT NULL,
                config_fingerprint VARCHAR NOT NULL,
                random_seed BIGINT,
                start_year INTEGER NOT NULL,
                end_year INTEGER NOT NULL,
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                planalign_version VARCHAR,
                full_reset BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )


def _create_feature_119_execution_schema(database: Path) -> None:
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            """
            CREATE TABLE run_execution_metadata (
                run_id VARCHAR NOT NULL,
                recorded_at TIMESTAMP NOT NULL,
                status VARCHAR NOT NULL,
                execution_engine VARCHAR NOT NULL,
                direct_invocation_count INTEGER NOT NULL,
                delegated_invocation_count INTEGER NOT NULL,
                unexpected_fallback_count INTEGER NOT NULL,
                reason_counts_json VARCHAR NOT NULL,
                render_context_digests_json VARCHAR NOT NULL,
                parity_status VARCHAR NOT NULL,
                peak_rss_mb DOUBLE
            )
            """
        )
        conn.execute(
            """
            INSERT INTO run_execution_metadata VALUES (
                ?, current_timestamp, 'success', 'dbt', 0, 0, 0,
                '{}', '[]', 'not_run', NULL
            )
            """,
            [LEGACY_RUN_ID],
        )


def _create_broken_feature_120_execution_schema(database: Path) -> None:
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            """
            CREATE TABLE run_execution_metadata (
                run_id VARCHAR NOT NULL,
                recorded_at TIMESTAMP NOT NULL,
                invocation_count INTEGER NOT NULL,
                schedule_steps VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO run_execution_metadata VALUES (
                ?, current_timestamp, 1, '[]'
            )
            """,
            [LEGACY_RUN_ID],
        )


def test_old_schema_evolves_and_records_start_then_terminal_schedule(tmp_path):
    database = tmp_path / "old-schema.duckdb"
    _create_old_schema(database)
    manager = DatabaseConnectionManager(database)
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    signature = _signature(database)
    run_id = str(uuid.uuid4())

    check_and_record_run(
        manager,
        config,
        start_year=2025,
        end_year=2025,
        run_type="simulate",
        run_id=run_id,
        construction_signature=signature,
    )
    schedule = WorkSchedule()
    schedule.record(
        command="run --select tag:FOUNDATION",
        stage="FOUNDATION",
        year=2025,
        runner_kind="dbt",
    )
    append_execution_record(manager, run_id=run_id, schedule=schedule)

    with manager.get_connection() as conn:
        start = conn.execute(
            """
            SELECT construction_signature_hash, initialization_policy,
                   entry_point, runner_kind
            FROM run_metadata WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        terminal = conn.execute(
            """
            SELECT invocation_count, schedule_steps
            FROM run_execution_metadata WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()

    assert start == (signature.signature_hash, "none", "cli.simulate", "dbt")
    assert terminal is not None
    assert terminal[0] == 1
    assert json.loads(terminal[1]) == [
        {
            "command": "run --select tag:FOUNDATION",
            "runner_kind": "dbt",
            "seq": 1,
            "stage": "FOUNDATION",
            "year": 2025,
        }
    ]


def test_feature_119_terminal_schema_evolves_without_losing_its_contract(tmp_path):
    database = tmp_path / "feature-119-schema.duckdb"
    _create_old_schema(database)
    _create_feature_119_execution_schema(database)
    manager = DatabaseConnectionManager(database)
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    signature = _signature(database)
    run_id = str(uuid.uuid4())

    check_and_record_run(
        manager,
        config,
        start_year=2025,
        end_year=2025,
        run_type="simulate",
        run_id=run_id,
        construction_signature=signature,
    )
    schedule = WorkSchedule()
    schedule.record(
        command="run --select tag:FOUNDATION",
        stage="FOUNDATION",
        year=2025,
        runner_kind="dbt",
    )
    append_execution_record(
        manager,
        run_id=run_id,
        schedule=schedule,
        execution_engine="dbt",
    )

    with manager.get_connection() as conn:
        terminal = conn.execute(
            """
            SELECT status, execution_engine, direct_invocation_count,
                   delegated_invocation_count, unexpected_fallback_count,
                   reason_counts_json, render_context_digests_json,
                   parity_status, peak_rss_mb, invocation_count, schedule_steps
            FROM run_execution_metadata WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        legacy = conn.execute(
            """
            SELECT status, invocation_count, schedule_steps
            FROM run_execution_metadata WHERE run_id = ?
            """,
            [LEGACY_RUN_ID],
        ).fetchone()

    assert terminal is not None
    assert terminal[:10] == (
        "success",
        "dbt",
        0,
        0,
        0,
        "{}",
        "[]",
        "not_run",
        None,
        1,
    )
    assert json.loads(terminal[10])[0]["command"] == "run --select tag:FOUNDATION"
    assert legacy == ("success", None, None)


def test_early_feature_120_terminal_schema_converges_to_combined_shape(tmp_path):
    database = tmp_path / "early-feature-120-schema.duckdb"
    _create_old_schema(database)
    _create_broken_feature_120_execution_schema(database)
    manager = DatabaseConnectionManager(database)
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    run_id = str(uuid.uuid4())

    check_and_record_run(
        manager,
        config,
        start_year=2025,
        end_year=2025,
        run_type="simulate",
        run_id=run_id,
        construction_signature=_signature(database),
    )
    append_execution_record(
        manager,
        run_id=run_id,
        schedule=WorkSchedule(),
        execution_engine="dbt",
    )

    with manager.get_connection() as conn:
        current = conn.execute(
            """
            SELECT status, execution_engine, invocation_count, schedule_steps
            FROM run_execution_metadata WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        legacy = conn.execute(
            """
            SELECT status, execution_engine, invocation_count, schedule_steps
            FROM run_execution_metadata WHERE run_id = ?
            """,
            [LEGACY_RUN_ID],
        ).fetchone()

    assert current == ("success", "dbt", 0, "[]")
    assert legacy == ("success", "dbt", 1, "[]")


def test_required_construction_provenance_failure_is_loud(monkeypatch, tmp_path):
    database = tmp_path / "failure.duckdb"
    manager = DatabaseConnectionManager(database)
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    run_id = str(uuid.uuid4())

    def fail_schema(_conn):
        raise duckdb.IOException("forced schema failure")

    monkeypatch.setattr(
        "planalign_orchestrator.run_metadata._evolve_provenance_schema", fail_schema
    )

    with pytest.raises(RunMetadataError, match=run_id):
        check_and_record_run(
            manager,
            config,
            start_year=2025,
            end_year=2025,
            run_type="simulate",
            run_id=run_id,
            construction_signature=_signature(database),
        )
