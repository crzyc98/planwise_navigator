import hashlib
from pathlib import Path

import pytest

from planalign_api.services.provenance.render import canonical_payload, render_markdown
from planalign_api.services.provenance.report import build_provenance_report
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
