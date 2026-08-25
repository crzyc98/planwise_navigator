"""Source-level contract checks for the run-health summary Studio surfaces."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

ROOT = Path(__file__).parents[2] / "planalign_studio"


def test_api_client_exposes_scenario_scoped_run_health() -> None:
    source = (ROOT / "services" / "api.ts").read_text(encoding="utf-8")
    assert "export interface RunHealthReport" in source
    assert "'missing_provenance'" in source
    assert "`/api/scenarios/${scenarioId}/runs/${runId}/health`" in source
    assert "`/api/scenarios/${scenarioId}/run-health`" in source


def test_simulation_detail_renders_per_run_health() -> None:
    source = (ROOT / "components" / "SimulationDetail.tsx").read_text(encoding="utf-8")
    assert "<RunHealthSummary" in source
    assert "runId={run.id}" in source


def test_analytics_dashboard_renders_compact_health_strip() -> None:
    source = (ROOT / "components" / "AnalyticsDashboard.tsx").read_text(
        encoding="utf-8"
    )
    assert "<RunHealthSummary" in source
    assert "compact" in source


def test_health_summary_distinguishes_all_states() -> None:
    source = (ROOT / "components" / "simulation" / "RunHealthSummary.tsx").read_text(
        encoding="utf-8"
    )
    assert "data-run-health-status" in source
    for status in (
        "'clean'",
        "'warnings'",
        "'failed'",
        "'missing_provenance'",
        "'unavailable'",
    ):
        assert status in source
    # Missing artifact must not read like a clean run.
    assert "different from a clean run" in source
    assert "unverified rather than clean" in source


def test_health_summary_lists_findings_and_links_audit_report() -> None:
    source = (ROOT / "components" / "simulation" / "RunHealthSummary.tsx").read_text(
        encoding="utf-8"
    )
    for label in ("Rule", "Disposition", "Year / Stage", "Records", "Summary"):
        assert label in source
    assert "View full audit report" in source
    assert "/runs/${runId}/provenance" in source


def test_health_summary_uses_scenario_bound_client_function() -> None:
    source = (ROOT / "components" / "simulation" / "RunHealthSummary.tsx").read_text(
        encoding="utf-8"
    )
    assert "getRunHealth(scenarioId, runId)" in source
    assert "getRunProvenance(" not in source
