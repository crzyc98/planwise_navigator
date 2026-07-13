import time
from pathlib import Path

import pytest

from planalign_api.services.provenance.render import render_json, render_markdown
from planalign_api.services.provenance.report import build_provenance_report
from tests.fixtures.run_provenance import RUN_ID, build_archive

pytestmark = pytest.mark.fast


def test_typical_report_is_bounded_and_fast(tmp_path: Path):
    build_archive(tmp_path)
    started = time.perf_counter()
    report = build_provenance_report(tmp_path, RUN_ID)
    output = (render_json(report) + render_markdown(report)).encode()
    assert time.perf_counter() - started < 2.0
    assert len(output) < 5 * 1024 * 1024
