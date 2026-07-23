"""Contracts for Feature 122 frozen-baseline evidence."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from planalign_orchestrator.state_pipeline_validation import (
    CharacterizationRecord,
    ExclusionManifest,
    FileGuard,
    PhaseGateRecord,
    assert_phase_continuity,
    canonical_fingerprint,
    load_exclusion_manifest,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def _characterization() -> CharacterizationRecord:
    return CharacterizationRecord(
        baseline_id="f122-ab-c6ad648",
        code_fingerprint=HASH_A,
        normalized_config_fingerprint=HASH_A,
        census_fingerprint=HASH_A,
        seed_fingerprint=HASH_A,
        construction_fingerprint=HASH_A,
        database_fingerprint=HASH_A,
        horizon=(2025, 2029),
        census_rows=60_040,
        aggregate={"event_count": 123},
    )


def test_characterization_is_versioned_typed_and_canonical():
    record = _characterization()

    assert record.schema_version == 1
    assert canonical_fingerprint({"b": 2, "a": 1}) == canonical_fingerprint(
        {"a": 1, "b": 2}
    )
    assert (
        CharacterizationRecord.model_validate_json(record.model_dump_json()) == record
    )


def test_phase_gate_rejects_baseline_drift_and_out_of_order_checkpoint():
    baseline = _characterization()
    first = PhaseGateRecord(
        phase="baseline_characterization",
        status="passed",
        baseline_id=baseline.baseline_id,
        candidate_fingerprint=HASH_B,
        artifact_labels=["baseline_characterization/reference"],
    )
    assert_phase_continuity(baseline, [], first)

    wrong_id = first.model_copy(
        update={"phase": "run_database_isolation", "baseline_id": "different"}
    )
    with pytest.raises(ValueError, match="baseline_id"):
        assert_phase_continuity(baseline, [first], wrong_id)

    skipped = first.model_copy(update={"phase": "event_publication"})
    with pytest.raises(ValueError, match="ordered"):
        assert_phase_continuity(baseline, [first], skipped)


def test_checkpoint_order_is_enforced_within_consumer_migration():
    baseline = _characterization()
    previous = [
        PhaseGateRecord(
            phase=phase,
            status="passed",
            baseline_id=baseline.baseline_id,
            candidate_fingerprint=HASH_B,
            artifact_labels=[phase],
        )
        for phase in (
            "baseline_characterization",
            "run_database_isolation",
            "event_publication",
            "shadow_workforce/accumulator",
            "shadow_workforce/projection",
        )
    ]
    skipped = PhaseGateRecord(
        phase="consumers_migrated/employee_contributions",
        status="passed",
        baseline_id=baseline.baseline_id,
        candidate_fingerprint=HASH_B,
        artifact_labels=["consumer/contributions"],
    )

    with pytest.raises(ValueError, match="ordered"):
        assert_phase_continuity(baseline, previous, skipped)


def test_exclusion_loader_rejects_duplicates_unknown_relations_and_empty_reason(
    tmp_path: Path,
):
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        "schema_version: 1\nexclusions:\n"
        "  - {relation: fct_a, column: created_at, reason: one}\n"
        "  - {relation: fct_a, column: created_at, reason: two}\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_exclusion_manifest(duplicate, known_relations={"fct_a"})

    manifest = ExclusionManifest(
        exclusions=[{"relation": "fct_unknown", "column": "created_at", "reason": "x"}]
    )
    with pytest.raises(ValueError, match="unknown relation"):
        manifest.validate_known_relations({"fct_a"})

    with pytest.raises(ValidationError):
        ExclusionManifest(
            exclusions=[{"relation": "fct_a", "column": "created_at", "reason": ""}]
        )


@pytest.mark.parametrize(
    "unsafe",
    [
        "/private/tmp/reference.duckdb",
        "data/census.parquet",
        "employee_ssn",
        "INV_EMP_0001",
    ],
)
def test_checked_records_reject_paths_and_employee_content(unsafe: str):
    with pytest.raises(ValidationError):
        PhaseGateRecord(
            phase="baseline_characterization",
            status="passed",
            baseline_id="f122-ab-c6ad648",
            candidate_fingerprint=HASH_A,
            artifact_labels=[unsafe],
        )


def test_file_guard_distinguishes_absent_and_present_files(tmp_path: Path):
    path = tmp_path / "guarded.duckdb"
    absent = FileGuard.capture("shared_dev_db", path)
    path.write_bytes(b"safe aggregate fixture")
    present = FileGuard.capture("shared_dev_db", path)

    assert absent.exists is False and absent.sha256 is None
    assert present.exists is True and present.sha256 != absent.sha256
