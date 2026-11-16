"""Contract tests for the traceable report surface."""

from datetime import datetime, timezone

from planalign_api.models.report import (
    ReportPlanDesign,
    ReportProvenance,
    ReportScenario,
    ReportYear,
    ScenarioReport,
)
from planalign_api.services.report_render import render_html


def _design(text: str) -> ReportPlanDesign:
    return ReportPlanDesign(
        eligibility=text, auto_enrollment=text, escalation=text, match=text, core=text
    )


def test_report_html_contains_metrics_and_traceability_footer():
    report = ScenarioReport(
        title="Baseline <report>",
        generated_at=datetime.now(timezone.utc),
        anchor_scenario_id="scenario",
        scenarios=[
            ReportScenario(
                scenario_id="scenario",
                name="Baseline",
                is_anchor=True,
                design=_design("Immediate."),
                years=[
                    ReportYear(
                        year=2025,
                        employer_cost=125000,
                        cost_pct_of_capped_pay=4.25,
                        participation_rate=62.5,
                        average_deferral_rate=None,
                    )
                ],
                total_employer_cost=125000,
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

    html = render_html(report, None)

    assert "2025" in html
    assert "$125,000" in html and "4.25%" in html and "62.5%" in html
    assert "—" in html  # unavailable deferral renders as a dash, not 0
    assert "Baseline &lt;report&gt;" in html  # user text is escaped
    assert "scenario / config " + "a" * 12 in html
    assert html.count("data:image/png;base64,") == 1
    assert "display:grid" not in html
