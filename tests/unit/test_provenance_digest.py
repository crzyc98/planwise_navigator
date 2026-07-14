import hashlib
import math
import unicodedata
from pathlib import Path

import pytest

from planalign_api.services.provenance.render import canonical_payload
from planalign_api.services.provenance.report import build_provenance_report
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.fast


def test_digest_is_deterministic_and_excludes_signoff(tmp_path: Path):
    build_archive(tmp_path)
    first = build_provenance_report(tmp_path, RUN_ID)
    second = build_provenance_report(tmp_path, RUN_ID)
    assert first.digest.value == second.digest.value
    first.sign_off.reviewer_name = "Reviewer"
    first.sign_off.decision = "approved"
    assert hashlib.sha256(canonical_payload(first)).hexdigest() == first.digest.value


def test_covered_evidence_changes_digest(tmp_path: Path):
    build_archive(tmp_path)
    report = build_provenance_report(tmp_path, RUN_ID)
    before = report.digest.value
    report.evidence.event_counts[0].count = 1
    assert hashlib.sha256(canonical_payload(report)).hexdigest() != before


def test_canonicalization_sorts_semantic_lists_and_includes_nulls(tmp_path: Path):
    build_archive(tmp_path)
    report = build_provenance_report(tmp_path, RUN_ID)
    report.evidence.event_counts.append(
        report.evidence.event_counts[0].model_copy(update={"event_type": "ALPHA"})
    )
    forward = canonical_payload(report)
    report.evidence.event_counts.reverse()
    assert canonical_payload(report) == forward
    assert b'"working_tree_fingerprint":null' in forward


def test_canonicalization_uses_unicode_nfc_and_rejects_nonfinite(tmp_path: Path):
    build_archive(tmp_path)
    report = build_provenance_report(tmp_path, RUN_ID)
    report.evidence.run.scenario_id = "Cafe\u0301"
    payload = canonical_payload(report)
    assert unicodedata.normalize("NFC", "Cafe\u0301").encode() in payload
    report.evidence.configuration.effective = {"bad": math.nan}
    with pytest.raises(ValueError, match="finite"):
        canonical_payload(report)
