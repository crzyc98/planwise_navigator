"""Canonical portable evidence-pack text tests."""

import pytest

from planalign_evidence.render import build_envelope, render_evidence_pack
from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from tests.fixtures.evidence_pack import create_evidence_scenario


@pytest.mark.fast
def test_renderer_is_complete_deterministic_and_path_safe(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    pack = build_evidence_pack(target, "total_compensation", 2025, 2027)

    text = render_evidence_pack(pack)
    envelope = build_envelope(pack)

    assert text == render_evidence_pack(pack) == envelope.text_export
    assert text.endswith("\n") and not text.endswith("\n\n")
    for heading in (
        "## Provenance",
        "## Warnings",
        "## Movement",
        "## Driver decomposition",
        "## Residual",
        "## Population treatment",
        "## Citations",
    ):
        assert heading in text
    assert text.count("```sql") == 1
    assert scenario.run_id in text
    assert str(tmp_path) not in text
    assert envelope.filename.endswith(".md")
