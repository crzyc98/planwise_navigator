"""Isolated archived-run builders for provenance tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import duckdb

from planalign_api.models.provenance import (
    AnnualEventCount,
    AnnualWorkforceReconciliation,
    CapturedValidationResult,
    ConfigurationEvidence,
    ExecutionTimingEvidence,
    InputFingerprint,
    RunIdentityEvidence,
    RunProvenanceManifest,
    SeedFingerprint,
    SoftwareEvidence,
)
from planalign_api.services.provenance.capture import config_fingerprint

RUN_ID = "12345678-1234-5678-9234-567812345678"
HASH_A = "a" * 64
HASH_B = "b" * 64


def build_archive(
    root: Path, *, run_id: str = RUN_ID, status: str = "completed", legacy: bool = False
) -> Path:
    run_dir = root / "workspace" / "scenarios" / "scenario-a" / "runs" / run_id
    run_dir.mkdir(parents=True)
    metadata = {
        "run_id": run_id,
        "workspace_id": "workspace",
        "scenario_id": "scenario-a",
        "status": status,
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T00:01:00Z",
        "duration_seconds": 60,
        "start_year": 2025,
        "end_year": 2025,
        "seed": 7,
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2025\n  random_seed: 7\nplan_design_id: plan-a\n",
        encoding="utf-8",
    )
    if not legacy:
        started = datetime(2025, 1, 1, tzinfo=timezone.utc)
        capture_state = status if status in {"failed", "cancelled"} else "completed"
        effective_config = {
            "simulation": {"start_year": 2025, "end_year": 2025, "random_seed": 7},
            "plan_design_id": "plan-a",
        }
        manifest = RunProvenanceManifest(
            run_id=UUID(run_id),
            capture_state=capture_state,
            run_identity=RunIdentityEvidence(
                run_id=UUID(run_id),
                workspace_id="workspace",
                scenario_id="scenario-a",
                plan_design_id="plan-a",
                status=status,
                intended_start_year=2025,
                intended_end_year=2025,
                completed_years=[2025],
            ),
            execution_timing=ExecutionTimingEvidence(
                started_at=started,
                completed_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
                duration_seconds=60,
                terminal_stage="REPORTING",
            ),
            software=SoftwareEvidence(
                planalign_version="1.0.0",
                git_commit_sha="c" * 40,
                working_tree_state="clean",
            ),
            configuration=ConfigurationEvidence(
                effective=effective_config,
                fingerprint=config_fingerprint(effective_config),
                fingerprint_method="sha256-canonical-effective-config-v1",
            ),
            random_seed=7,
            census_input=InputFingerprint(
                logical_name="census.parquet",
                sha256=HASH_B,
                size_bytes=100,
                record_count=10,
                format="parquet",
            ),
            seed_files=[
                SeedFingerprint(logical_name="config.csv", sha256=HASH_A, size_bytes=20)
            ],
            event_counts=[
                AnnualEventCount(simulation_year=2025, event_type="TOTAL", count=0)
            ],
            workforce_reconciliations=[
                AnnualWorkforceReconciliation(
                    simulation_year=2025,
                    opening_workforce=10,
                    hires=0,
                    terminations=0,
                    expected_closing_workforce=10,
                    actual_closing_workforce=10,
                    variance=0,
                    opening_source="baseline",
                )
            ],
            validation_results=[
                CapturedValidationResult(
                    simulation_year=2025,
                    check_name="event_sequence_validation",
                    severity="error",
                    passed=True,
                    affected_record_count=0,
                )
            ],
            validation_disposition="passed",
            started_at=started,
            finalized_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
        )
        (run_dir / "provenance.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
    return run_dir


def build_legacy_archive(root: Path) -> Path:
    return build_archive(root, legacy=True)


def build_failed_archive(root: Path) -> Path:
    return build_archive(root, status="failed")


def build_cancelled_archive(root: Path) -> Path:
    return build_archive(root, status="cancelled")


def build_partial_archive(root: Path) -> Path:
    run_dir = build_archive(root, status="failed")
    manifest = RunProvenanceManifest.model_validate_json(
        (run_dir / "provenance.json").read_text(encoding="utf-8")
    )
    manifest.run_identity.completed_years = []
    manifest.event_counts = []
    manifest.workforce_reconciliations = []
    manifest.validation_results = []
    manifest.validation_disposition = "incomplete"
    (run_dir / "provenance.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return run_dir


def build_malformed_archive(root: Path) -> Path:
    run_dir = build_archive(root)
    (run_dir / "provenance.json").write_text("{malformed", encoding="utf-8")
    return run_dir


def build_duplicate_archives(root: Path) -> tuple[Path, Path]:
    return build_archive(root / "one"), build_archive(root / "two")


def add_minimal_archived_database(run_dir: Path) -> Path:
    """Create aggregate-only archived tables; report tests assert they are never queried."""
    database = run_dir / "simulation.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE fct_yearly_events(event_type VARCHAR, simulation_year INTEGER)"
        )
        connection.execute(
            "CREATE TABLE fct_workforce_snapshot(simulation_year INTEGER, employment_status VARCHAR)"
        )
    return database
