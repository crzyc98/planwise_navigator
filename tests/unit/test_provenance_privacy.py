from pathlib import Path

import pytest

from planalign_api.services.provenance.render import render_json, render_markdown
from planalign_api.services.provenance.report import build_provenance_report
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.fast


def test_report_has_no_employee_rows_or_physical_paths(tmp_path: Path):
    build_archive(tmp_path)
    report = build_provenance_report(tmp_path, RUN_ID)
    output = render_json(report) + render_markdown(report)
    for forbidden in ("employee_id", str(tmp_path), str(Path.home()), "census rows"):
        assert forbidden not in output
