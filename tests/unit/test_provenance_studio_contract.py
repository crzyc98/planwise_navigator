"""Source-level contract checks for the dependency-free Studio frontend build."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

ROOT = Path(__file__).parents[2] / "planalign_studio"


def test_run_history_exposes_view_and_download_actions() -> None:
    source = (ROOT / "components" / "SimulationDetail.tsx").read_text(encoding="utf-8")
    assert "View Provenance" in source
    assert "Download Audit Report" in source
    assert "isArchivedProvenanceRun(run)" in source
    assert "downloadRunProvenanceBundle(runId)" in source


def test_view_route_and_required_audit_sections_are_registered() -> None:
    app = (ROOT / "App.tsx").read_text(encoding="utf-8")
    viewer = (ROOT / "components" / "RunProvenanceReport.tsx").read_text(
        encoding="utf-8"
    )
    assert 'path="simulate/:scenarioId/runs/:runId/provenance"' in app
    for section in (
        "Missing or Unavailable Evidence",
        "Run Identity and Execution",
        "Software, Source, and Configuration",
        "Input Fingerprints",
        "Event Counts by Year",
        "Annual Workforce Reconciliation",
        "Captured Validation Results",
        "Integrity Verification and Reviewer Sign-Off",
    ):
        assert section in viewer


def test_provenance_downloads_use_authenticated_api_client() -> None:
    source = (ROOT / "services" / "api.ts").read_text(encoding="utf-8")
    assert "fetchWithAuth(`${API_BASE}/api/runs/${runId}/provenance`" in source
    assert "headers: { Accept: 'application/zip' }" in source
    assert "headers: { Accept: 'application/json' }" in source
