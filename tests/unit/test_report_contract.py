"""Contract tests for the traceable report surface."""

from datetime import datetime, timezone

from planalign_api.models.report import (
    ReportProvenance,
    ReportYearMetrics,
    ScenarioReport,
)
from planalign_api.services.report_service import _render_html


def test_report_html_contains_metrics_and_traceability_footer():
    report = ScenarioReport(
        title="Baseline report",
        generated_at=datetime.now(timezone.utc),
        years=[
            ReportYearMetrics(
                year=2025,
                headcount=100,
                average_compensation=75000,
                participation_rate=62.5,
                employer_cost=125000,
            )
        ],
        provenance=[
            ReportProvenance(
                workspace_id="ws",
                scenario_id="scenario",
                scenario_name="Baseline",
                run_id="run-1",
                config_fingerprint="a" * 12,
                random_seed=42,
                git_sha="b" * 40,
            )
        ],
    )

    html = _render_html(report, None)

    assert "2025" in html
    assert "$75,000" in html
    assert "scenario / config " + "a" * 12 in html
    assert html.count("data:image/png;base64,") == 4
    assert "display:grid" not in html
