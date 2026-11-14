"""Plan-design comparison report: assembly, anchor, missing results, API and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from planalign_api import config as api_config
from planalign_api.models.scenario import Scenario, ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.report_render import (
    lead_lines,
    render_html,
    render_report,
    report_tables,
)
from planalign_api.services.report_service import (
    ReportAnchorError,
    ReportNotFoundError,
    ReportRequestError,
    build_scenario_report,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast]

ENDPOINT = "/api/workspaces/{ws}/scenarios/{sid}/report"

BASELINE_DESIGN = {
    "eligibility_months": 3,
    "auto_enroll": True,
    "auto_enroll_scope": "new_hires_only",
    "default_deferral_percent": 3.0,
    "auto_escalation": True,
    "escalation_mode": "automatic",
    "escalation_rate_percent": 1.0,
    "escalation_cap_percent": 10.0,
    "match_enabled": True,
    "match_status": "deferral_based",
    "match_tiers": [
        {"employee_min": 0.0, "employee_max": 0.03, "match_rate": 1.0},
        {"employee_min": 0.03, "employee_max": 0.05, "match_rate": 0.5},
    ],
    "match_min_hours_annual": 1000,
    "match_require_year_end_active": True,
    "core_enabled": True,
    "core_status": "flat",
    "core_contribution_rate_percent": 2.0,
}
RICHER_DESIGN = {
    **BASELINE_DESIGN,
    "eligibility_months": 0,
    "default_deferral_percent": 6.0,
    "match_tiers": [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}],
    "match_min_hours_annual": 0,
    "match_require_year_end_active": False,
    "core_enabled": False,
}
SWEEP_DESIGN = {**BASELINE_DESIGN, "auto_enroll_scope": "all_eligible"}

SNAPSHOT_DDL = """
    CREATE TABLE fct_workforce_snapshot (
        employee_id VARCHAR,
        simulation_year INTEGER,
        employment_status VARCHAR,
        termination_date DATE,
        employee_hire_date DATE,
        current_eligibility_status VARCHAR DEFAULT 'eligible',
        is_enrolled_flag BOOLEAN,
        prorated_annual_contributions DECIMAL(12, 2) DEFAULT 0,
        employer_match_amount DECIMAL(12, 2) DEFAULT 0,
        employer_core_amount DECIMAL(12, 2) DEFAULT 0,
        current_deferral_rate DECIMAL(6, 4) DEFAULT 0,
        effective_annual_deferral_rate DECIMAL(6, 4) DEFAULT 0,
        prorated_annual_compensation DECIMAL(12, 2) DEFAULT 0,
        participation_status_detail VARCHAR DEFAULT 'voluntary',
        has_deferral_escalations BOOLEAN DEFAULT FALSE,
        total_deferral_escalations INTEGER DEFAULT 0,
        total_escalation_amount DECIMAL(8, 4) DEFAULT 0,
        irs_limit_reached BOOLEAN DEFAULT FALSE
    );
    CREATE TABLE config_irs_limits (limit_year INTEGER, compensation_limit DECIMAL(12, 2));
    INSERT INTO config_irs_limits VALUES (2025, 350000), (2026, 360000);
    CREATE TABLE run_metadata (
        run_id VARCHAR, run_timestamp TIMESTAMP, run_type VARCHAR,
        config_fingerprint VARCHAR, random_seed INTEGER, full_reset BOOLEAN,
        planalign_version VARCHAR
    );
"""


def _build_db(path: Path, match_scale: float, run_id: str) -> None:
    """Three employees over 2025-2026; ``match_scale`` varies employer cost."""
    rows = [
        ("e1", 2025, True, 3000, 1500, 500, 0.06, 100000),
        ("e1", 2026, True, 3200, 1600, 520, 0.06, 104000),
        ("e2", 2025, False, 0, 0, 400, 0.0, 60000),
        ("e2", 2026, True, 1200, 600, 410, 0.03, 62000),
        ("e3", 2025, True, 25000, 9000, 4000, 0.05, 500000),
        ("e3", 2026, True, 26000, 9500, 4100, 0.05, 510000),
    ]
    conn = duckdb.connect(str(path))
    try:
        conn.execute(SNAPSHOT_DDL)
        for emp, year, enrolled, deferrals, match, core, rate, comp in rows:
            conn.execute(
                "INSERT INTO fct_workforce_snapshot (employee_id, simulation_year, "
                "employment_status, employee_hire_date, is_enrolled_flag, "
                "prorated_annual_contributions, employer_match_amount, "
                "employer_core_amount, current_deferral_rate, "
                "effective_annual_deferral_rate, prorated_annual_compensation) "
                "VALUES (?, ?, 'ACTIVE', DATE '2020-01-01', ?, ?, ?, ?, ?, ?, ?)",
                [
                    emp,
                    year,
                    enrolled,
                    deferrals,
                    match * match_scale,
                    core,
                    rate,
                    rate,
                    comp,
                ],
            )
        conn.execute(
            "INSERT INTO run_metadata VALUES (?, TIMESTAMP '2026-11-01 12:00:00', "
            "'simulation', 'abc123def456', 42, TRUE, '0.0.0')",
            [run_id],
        )
    finally:
        conn.close()


@dataclass
class Env:
    storage: WorkspaceStorage
    workspace_id: str
    baseline: Scenario
    richer: Scenario
    unrun: Scenario


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    storage = WorkspaceStorage(settings.workspaces_root)
    workspace = storage.create_workspace(WorkspaceCreate(name="Client"), {})

    def scenario(name: str, design: dict) -> Scenario:
        created = storage.create_scenario(
            workspace.id,
            ScenarioCreate(name=name, config_overrides={"dc_plan": design}),
        )
        assert created is not None
        return created

    baseline = scenario("Baseline", BASELINE_DESIGN)
    richer = scenario("Richer Match", RICHER_DESIGN)
    unrun = scenario("Re-enroll All", SWEEP_DESIGN)
    for item, scale in ((baseline, 1.0), (richer, 1.5)):
        storage.update_scenario_status(workspace.id, item.id, "completed")
        _build_db(
            storage._scenario_path(workspace.id, item.id) / "simulation.duckdb",
            scale,
            f"run-{item.name}",
        )
    return Env(storage, workspace.id, baseline, richer, unrun)


def _comparison(env: Env, anchor: str | None = None):
    return build_scenario_report(
        env.storage,
        env.workspace_id,
        env.baseline.id,
        [env.richer.id, env.unrun.id],
        anchor=anchor,
    )


def test_figures_equal_analytics_service_and_differences_use_anchor(env):
    report = _comparison(env)
    analytics = {
        s.id: AnalyticsService(env.storage).get_dc_plan_analytics(
            env.workspace_id, s.id, s.name
        )
        for s in (env.baseline, env.richer)
    }
    by_id = {s.scenario_id: s for s in report.scenarios}
    for scenario_id, source in analytics.items():
        section = by_id[scenario_id]
        assert section.total_employer_cost == source.total_employer_cost
        assert (
            section.total_cost_pct_of_capped_pay
            == source.employer_cost_pct_of_capped_compensation
        )
        for year, expected in zip(section.years, source.contribution_by_year):
            assert year.employer_cost == expected.total_employer_cost
            assert (
                year.cost_pct_of_capped_pay
                == expected.employer_cost_pct_of_capped_compensation
            )
            assert year.participation_rate == expected.participation_rate
            assert year.average_deferral_rate == pytest.approx(
                expected.average_deferral_rate * 100
            )

    base, richer = analytics[env.baseline.id], analytics[env.richer.id]
    section = by_id[env.richer.id]
    assert report.anchor_scenario_id == env.baseline.id
    assert section.total_difference_from_anchor == pytest.approx(
        richer.total_employer_cost - base.total_employer_cost
    )
    assert [y.difference_from_anchor for y in section.years] == pytest.approx(
        [
            r.total_employer_cost - b.total_employer_cost
            for r, b in zip(richer.contribution_by_year, base.contribution_by_year)
        ]
    )
    assert by_id[env.baseline.id].total_difference_from_anchor is None


def test_designs_are_stated_in_plain_words(env):
    designs = {s.name: s.design for s in _comparison(env).scenarios}

    baseline = designs["Baseline"]
    assert baseline.eligibility == "Eligible to defer after 3 months of service."
    assert baseline.auto_enrollment == (
        "New hires are auto-enrolled at 3% of pay and may opt out."
    )
    assert baseline.escalation == "Deferrals rise 1% a year, up to 10% of pay."
    assert baseline.match == (
        "100% of the first 3%, then 50% of the next 2% deferred (up to 4% of pay). "
        "Requires 1,000 hours in the year and employment on the last day of the year."
    )
    assert baseline.core == "2% of pay, whether or not the employee defers."

    richer = designs["Richer Match"]
    assert richer.eligibility == "Eligible to defer immediately on hire."
    assert richer.match == "100% of the first 6% deferred (up to 6% of pay)."
    assert richer.core == "No core contribution."
    assert designs["Re-enroll All"].auto_enrollment.startswith(
        "All eligible employees, including current ones, are auto-enrolled"
    )


def test_missing_result_is_named_not_dropped(env):
    report = _comparison(env)
    unrun = next(s for s in report.scenarios if s.scenario_id == env.unrun.id)

    assert unrun.missing_reason == "Not run yet."
    assert unrun.years == [] and unrun.total_employer_cost is None
    html = render_html(report)
    assert "Not included (no usable result)" in html
    assert "Re-enroll All: Not run yet." in html
    assert "Re-enroll All (no result)" in html
    assert "$0" not in html


def test_lead_states_designs_and_cost_difference_first(env):
    report = _comparison(env)
    lead = lead_lines(report)
    assert lead[0] == (
        "3 plan designs compared over 2025–2026. "
        "Differences are measured against Baseline."
    )
    assert lead[2].startswith("Richer Match: $")
    assert "more than Baseline (+" in lead[2]
    titles = [t.title for t in report_tables(report)]
    assert titles[:3] == [
        "Plan designs",
        "Employer cost, 2025–2026",
        "Employer cost by year",
    ]
    assert "Difference from Baseline by year" in titles
    html = render_html(report)
    assert html.index("Plan designs") < html.index("Employer cost by year")
    assert html.index("Notes") < html.index("Appendix: provenance")
    assert "401(a)(17)" in html and "gross of forfeitures" in html


def test_anchor_parameter_changes_the_reference(env):
    report = _comparison(env, anchor="Richer Match")
    by_id = {s.scenario_id: s for s in report.scenarios}

    assert report.anchor_scenario_id == env.richer.id
    assert by_id[env.richer.id].total_difference_from_anchor is None
    assert by_id[env.baseline.id].total_difference_from_anchor < 0
    assert "less than Richer Match" in " ".join(lead_lines(report))


def test_invalid_anchor_and_too_many_scenarios_are_request_errors(env):
    with pytest.raises(ReportAnchorError, match="not one of the selected"):
        _comparison(env, anchor="Nonexistent")
    with pytest.raises(ReportRequestError, match="at most 6"):
        build_scenario_report(
            env.storage,
            env.workspace_id,
            env.baseline.id,
            [_extra(env, n).id for n in range(6)],
        )


def _extra(env: Env, index: int) -> Scenario:
    created = env.storage.create_scenario(
        env.workspace_id, ScenarioCreate(name=f"Extra {index}")
    )
    assert created is not None
    return created


def test_single_scenario_report_has_no_comparison_sections(env):
    report = build_scenario_report(env.storage, env.workspace_id, env.baseline.id)

    assert not report.is_comparison
    assert report.title == "Plan design and employer cost: Baseline"
    assert report.note("difference") is None
    html = render_html(report)
    assert "Difference from" not in html
    assert "(anchor)" not in html
    assert "Baseline: $" in html


def test_report_with_no_usable_result_is_not_found(env):
    with pytest.raises(ReportNotFoundError, match="Re-enroll All: Not run yet"):
        build_scenario_report(env.storage, env.workspace_id, env.unrun.id)


def test_pptx_carries_designs_costs_and_differences(env, tmp_path):
    pptx = pytest.importorskip("pptx")
    output = render_report(_comparison(env), tmp_path / "r.pptx", "pptx")
    text = "\n".join(
        shape.text_frame.text
        for slide in pptx.Presentation(str(output)).slides
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert "Plan design: Baseline (anchor)" in text
    assert "Employer match: 100% of the first 6% deferred" in text
    assert "Difference from Baseline by year" in text
    assert "Re-enroll All: Not run yet." in text


def test_route_accepts_anchor_and_rejects_invalid_one(env):
    from fastapi.testclient import TestClient

    from planalign_api.main import create_app

    client = TestClient(create_app())
    url = ENDPOINT.format(ws=env.workspace_id, sid=env.baseline.id)
    compare = f"{env.richer.id},{env.unrun.id}"

    ok = client.get(
        url, params={"format": "html", "compare": compare, "anchor": env.richer.id}
    )
    assert ok.status_code == 200
    assert "Differences are measured against Richer Match." in ok.text
    assert "Re-enroll All: Not run yet." in ok.text

    bad = client.get(url, params={"format": "html", "compare": compare, "anchor": "x"})
    assert bad.status_code == 400
    assert "not one of the selected scenarios" in bad.json()["detail"]


def test_cli_report_accepts_anchor(env, tmp_path):
    from typer.testing import CliRunner

    from planalign_cli.main import app

    output = tmp_path / "cli.html"
    args = [
        "report",
        env.baseline.id,
        "--workspace",
        env.workspace_id,
        "--compare",
        env.richer.id,
        "--format",
        "html",
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, [*args, "--anchor", "Richer Match"])
    assert result.exit_code == 0, result.output
    assert "Differences are measured against Richer Match." in output.read_text()

    bad = CliRunner().invoke(app, [*args, "--anchor", "nope"])
    assert bad.exit_code != 0
    assert "not one of the selected" in bad.output


def test_missing_anchor_leaves_differences_unavailable(env):
    report = _comparison(env, anchor=env.unrun.id)

    assert all(s.total_difference_from_anchor is None for s in report.scenarios)
    assert any(w.code == "anchor_unavailable" for w in report.warnings)
    assert "difference from Re-enroll All unavailable" in " ".join(lead_lines(report))
    assert "Difference from Re-enroll All by year" not in render_html(report)


def test_design_without_dc_plan_is_not_recorded_rather_than_assumed():
    from planalign_api.services.report_design import NOT_RECORDED, describe_plan_design

    design = describe_plan_design({"employer_match": {"active_formula": "simple"}})
    assert design.match == NOT_RECORDED and design.core == NOT_RECORDED
    partial = describe_plan_design({"dc_plan": {"match_enabled": False}})
    assert partial.match == "No employer match."
    assert partial.eligibility == NOT_RECORDED
