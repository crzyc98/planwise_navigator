import hashlib
import json
from pathlib import Path

import pytest

from planalign_api.services.provenance.render import canonical_payload, render_markdown
from planalign_api.services.provenance.report import build_provenance_report
from planalign_api.models.provenance import (
    AnnualEventCount,
    AnnualWorkforceReconciliation,
    CapturedValidationResult,
    RunProvenanceManifest,
)
from planalign_api.services.provenance.capture import config_fingerprint
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.integration


def test_archived_report_is_stable_after_current_state_changes(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in run_dir.iterdir()
    }
    current = tmp_path / "workspace" / "current-config.yaml"
    current.write_text("random_seed: 999\nemployee_id: forbidden\n", encoding="utf-8")
    first = build_provenance_report(tmp_path, RUN_ID)
    current.write_text("random_seed: 1\n", encoding="utf-8")
    second = build_provenance_report(tmp_path, RUN_ID)
    assert first == second
    assert first.verification_disposition == "fully_verified"
    assert hashlib.sha256(canonical_payload(first)).hexdigest() == first.digest.value
    assert first.digest.value in render_markdown(first)
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in run_dir.iterdir()
    }


def test_five_year_corrected_archive_is_fully_verified(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    provenance_path = run_dir / "provenance.json"
    manifest = RunProvenanceManifest.model_validate_json(
        provenance_path.read_text(encoding="utf-8")
    )
    years = list(range(2025, 2030))
    manifest.run_identity.intended_end_year = 2029
    manifest.run_identity.completed_years = years
    manifest.configuration.effective["simulation"]["end_year"] = 2029
    manifest.configuration.fingerprint = config_fingerprint(
        manifest.configuration.effective
    )
    manifest.event_counts = [
        AnnualEventCount(simulation_year=year, event_type="TOTAL", count=0)
        for year in years
    ]
    manifest.workforce_reconciliations = [
        AnnualWorkforceReconciliation(
            simulation_year=year,
            opening_workforce=10,
            hires=0,
            terminations=0,
            expected_closing_workforce=10,
            actual_closing_workforce=10,
            variance=0,
            opening_source="baseline" if year == 2025 else "prior_year_snapshot",
        )
        for year in years
    ]
    manifest.validation_results = [
        CapturedValidationResult(
            simulation_year=year,
            check_name="event_sequence_validation",
            severity="error",
            passed=True,
            affected_record_count=0,
        )
        for year in years
    ]
    provenance_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    metadata_path = run_dir / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["end_year"] = 2029
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2029\n  random_seed: 7\nplan_design_id: plan-a\n",
        encoding="utf-8",
    )

    report = build_provenance_report(tmp_path, RUN_ID)
    assert report.verification_disposition == "fully_verified"
    assert report.missing_evidence == []
    assert len(report.evidence.validation_results) == 5
    assert all(row.passed for row in report.evidence.validation_results)
    assert all(
        row.affected_record_count == 0 for row in report.evidence.validation_results
    )
    assert all(row.variance == 0 for row in report.evidence.workforce_reconciliations)
    assert hashlib.sha256(canonical_payload(report)).hexdigest() == report.digest.value
