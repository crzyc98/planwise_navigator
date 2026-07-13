import hashlib
from pathlib import Path

import pytest

from planalign_api.services.provenance.locator import (
    IdentityConflictError,
    RunNotFoundError,
)
from planalign_api.services.provenance.render import (
    canonical_payload,
    render_json,
    render_markdown,
)
from planalign_api.services.provenance.report import build_provenance_report
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.fast


def test_complete_archive_is_fully_verified_and_unchanged(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in run_dir.iterdir()}
    report = build_provenance_report(tmp_path, RUN_ID)
    assert report.verification_disposition == "fully_verified"
    assert report.evidence.event_counts[0].count == 0
    assert hashlib.sha256(canonical_payload(report)).hexdigest() == report.digest.value
    assert report.digest.value in render_json(report)
    assert report.digest.value in render_markdown(report)
    assert before == {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in run_dir.iterdir()
    }


def test_legacy_archive_is_unverifiable_without_current_fallback(tmp_path: Path):
    build_archive(tmp_path, legacy=True)
    report = build_provenance_report(tmp_path, RUN_ID)
    assert report.verification_disposition == "unverifiable"
    assert report.evidence.software.git_commit_sha is None
    assert report.evidence.configuration.fingerprint is None
    assert report.missing_evidence


def test_unknown_and_duplicate_run_ids_are_strict(tmp_path: Path):
    with pytest.raises(RunNotFoundError):
        build_provenance_report(tmp_path, RUN_ID)
    build_archive(tmp_path / "one")
    build_archive(tmp_path / "two")
    with pytest.raises(IdentityConflictError):
        build_provenance_report(tmp_path, RUN_ID)


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failed_or_cancelled_archive_is_incomplete_not_verified(
    tmp_path: Path, status: str
):
    build_archive(tmp_path, status=status)
    report = build_provenance_report(tmp_path, RUN_ID)
    assert report.evidence.run.status == status
    assert report.verification_disposition == "incomplete"


def test_malformed_manifest_is_unverifiable(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    (run_dir / "provenance.json").write_text("{malformed", encoding="utf-8")
    report = build_provenance_report(tmp_path, RUN_ID)
    assert report.verification_disposition == "unverifiable"
    assert any(
        item.field_path == "provenance_manifest" for item in report.missing_evidence
    )


def test_archived_configuration_tamper_is_reported(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    original = build_provenance_report(tmp_path, RUN_ID)
    (run_dir / "config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2025\n  random_seed: 999\nplan_design_id: plan-a\n",
        encoding="utf-8",
    )
    tampered = build_provenance_report(tmp_path, RUN_ID)
    assert tampered.verification_disposition == "unverifiable"
    assert tampered.digest.value != original.digest.value
    assert any(item.code == "integrity_mismatch" for item in tampered.missing_evidence)


def test_engine_event_types_are_supported(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    manifest_path = run_dir / "provenance.json"
    payload = manifest_path.read_text(encoding="utf-8")
    payload = payload.replace('"event_type": "TOTAL"', '"event_type": "RAISE"')
    manifest_path.write_text(payload, encoding="utf-8")
    report = build_provenance_report(tmp_path, RUN_ID)
    assert not any(
        finding.field_path.endswith("event_type") for finding in report.missing_evidence
    )
