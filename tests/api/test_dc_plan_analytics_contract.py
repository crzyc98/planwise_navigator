"""API contract tests for DC Plan cohort and eligible-population parameters.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_api import config as api_config
from planalign_api.main import create_app
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import analytics as analytics_router
from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast]

SINGLE_ENDPOINT = (
    "/api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan"
)
COMPARE_ENDPOINT = "/api/workspaces/{workspace_id}/analytics/dc-plan/compare"

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
    )
"""

# First simulation year resolves to 2025 (MIN(simulation_year)).
# e1: baseline (hired 2022), enrolled every year.
# e2: new hire (hired 2026), enrolled from 2026 onward.
ROWS = """
    INSERT INTO fct_workforce_snapshot (
        employee_id, simulation_year, employment_status, termination_date,
        employee_hire_date, current_eligibility_status,
        is_enrolled_flag, prorated_annual_contributions, employer_match_amount,
        employer_core_amount, current_deferral_rate, effective_annual_deferral_rate,
        prorated_annual_compensation
    ) VALUES
        ('e1', 2025, 'ACTIVE', NULL, DATE '2022-01-01', 'eligible', true, 3000, 1500, 500, 0.06, 0.06, 100000),
        ('e1', 2026, 'ACTIVE', NULL, DATE '2022-01-01', 'eligible', true, 3000, 1500, 500, 0.06, 0.06, 100000),
        ('e2', 2026, 'ACTIVE', NULL, DATE '2026-03-01', 'eligible', true, 2000, 1000, 300, 0.05, 0.05, 80000),
        ('e3', 2025, 'TERMINATED', DATE '2025-07-01', DATE '2020-01-01', 'eligible', true, 1000, 400, 100, 0.02, 0.02, 40000),
        ('e3', 2026, 'TERMINATED', DATE '2025-07-01', DATE '2020-01-01', 'eligible', true, 9999, 9999, 9999, 0.02, 0.02, 40000),
        ('p1', 2025, 'ACTIVE', NULL, DATE '2024-01-01', 'pending', false, 0, 0, 0, 0, 0, 70000)
"""


def _build_db(path: Path) -> Path:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(SNAPSHOT_DDL)
        conn.execute(ROWS)
    finally:
        conn.close()
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Workspace with two completed scenarios, each backed by its own database."""
    from fastapi.testclient import TestClient

    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)

    storage = WorkspaceStorage(settings.workspaces_root)
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenarios = []
    paths: dict[str, Path] = {}
    for name in ("Baseline", "Generous Match"):
        scenario = storage.create_scenario(workspace.id, ScenarioCreate(name=name))
        storage.update_scenario_status(workspace.id, scenario.id, "completed")
        paths[scenario.id] = _build_db(tmp_path / f"{scenario.id}.duckdb")
        scenarios.append(scenario)

    app = create_app()

    def _service() -> AnalyticsService:
        service = AnalyticsService(storage=storage)
        service.db_resolver = _StubResolver(paths)
        return service

    app.dependency_overrides[analytics_router.get_analytics_service] = _service
    return TestClient(app), workspace, scenarios


class _StubResolver:
    def __init__(self, paths: dict[str, Path]):
        self._paths = paths

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        path = self._paths.get(scenario_id, Path("/nonexistent.duckdb"))
        return ResolvedDatabasePath(
            path=path if path.exists() else None,
            source="scenario" if path.exists() else None,
        )


def test_cohort_all_is_byte_identical_to_no_cohort_param(env):
    """FR-007 / SC-003: default behavior is unchanged by this feature."""
    client, workspace, scenarios = env

    no_param = client.get(
        SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenarios[0].id)
    )
    explicit_all = client.get(
        SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenarios[0].id),
        params={"cohort": "all"},
    )

    assert no_param.status_code == 200
    assert explicit_all.status_code == 200
    assert no_param.json() == explicit_all.json()


@pytest.mark.parametrize("endpoint", ["single", "compare"])
def test_invalid_cohort_is_422(env, endpoint):
    """FR-013: an out-of-enum cohort value is rejected, not silently coerced."""
    client, workspace, scenarios = env

    if endpoint == "single":
        response = client.get(
            SINGLE_ENDPOINT.format(
                workspace_id=workspace.id, scenario_id=scenarios[0].id
            ),
            params={"cohort": "not_a_real_value"},
        )
    else:
        response = client.get(
            COMPARE_ENDPOINT.format(workspace_id=workspace.id),
            params={
                "scenarios": ",".join(s.id for s in scenarios),
                "cohort": "not_a_real_value",
            },
        )

    assert response.status_code == 422


@pytest.mark.parametrize("endpoint", ["single", "compare"])
def test_invalid_population_is_422(env, endpoint):
    client, workspace, scenarios = env
    if endpoint == "single":
        response = client.get(
            SINGLE_ENDPOINT.format(
                workspace_id=workspace.id, scenario_id=scenarios[0].id
            ),
            params={"population": "not_a_population"},
        )
    else:
        response = client.get(
            COMPARE_ENDPOINT.format(workspace_id=workspace.id),
            params={
                "scenarios": ",".join(s.id for s in scenarios),
                "population": "not_a_population",
            },
        )

    assert response.status_code == 422


def test_population_and_legacy_active_only_cannot_be_combined(env):
    client, workspace, scenarios = env
    response = client.get(
        SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenarios[0].id),
        params={"population": "active_eligible", "active_only": "true"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Use population or active_only, not both"


def test_explicit_populations_filter_eligibility_and_status(env):
    client, workspace, scenarios = env
    endpoint = SINGLE_ENDPOINT.format(
        workspace_id=workspace.id, scenario_id=scenarios[0].id
    )

    def rows(population: str) -> dict[int, dict]:
        response = client.get(endpoint, params={"population": population})
        assert response.status_code == 200
        return {row["year"]: row for row in response.json()["contribution_by_year"]}

    all_eligible = rows("all_eligible")
    active_eligible = rows("active_eligible")
    terminated_eligible = rows("terminated_eligible")

    assert all_eligible[2025]["total_eligible_count"] == 2
    assert active_eligible[2025]["total_eligible_count"] == 1
    assert terminated_eligible[2025]["total_eligible_count"] == 1
    assert terminated_eligible[2025]["total_employee_contributions"] == 1000.0
    assert all_eligible[2025]["employee_contribution_rate"] == round(
        4000 / 140000 * 100, 2
    )
    assert all_eligible[2025]["match_contribution_rate"] == round(
        1900 / 140000 * 100, 2
    )
    assert all_eligible[2025]["core_contribution_rate"] == round(600 / 140000 * 100, 2)

    # e3 remains TERMINATED in 2026 but terminated in 2025. The terms-only
    # trend retains the available year as an empty population and excludes the
    # carried-forward row and its deliberately conspicuous contribution value.
    assert terminated_eligible[2026]["total_eligible_count"] == 0
    assert terminated_eligible[2026]["total_employee_contributions"] == 0.0
    assert all_eligible[2026]["total_eligible_count"] == 2
    for year in (2025, 2026):
        assert all_eligible[year]["total_eligible_count"] == (
            active_eligible[year]["total_eligible_count"]
            + terminated_eligible[year]["total_eligible_count"]
        )

    terms_response = client.get(
        endpoint, params={"population": "terminated_eligible"}
    ).json()
    assert all(
        bucket["count"] == 0 for bucket in terms_response["deferral_rate_distribution"]
    )
    assert terms_response["escalation_metrics"]["employees_with_escalations"] == 0
    assert terms_response["irs_limit_metrics"]["employees_at_irs_limit"] == 0


def test_population_filter_applies_to_comparison_endpoint(env):
    client, workspace, scenarios = env
    response = client.get(
        COMPARE_ENDPOINT.format(workspace_id=workspace.id),
        params={
            "scenarios": ",".join(s.id for s in scenarios),
            "population": "active_eligible",
        },
    )

    assert response.status_code == 200
    for analytics in response.json()["analytics"]:
        rows = {row["year"]: row for row in analytics["contribution_by_year"]}
        assert rows[2025]["total_eligible_count"] == 1


def test_resolved_first_simulation_year_is_always_present(env):
    client, workspace, scenarios = env

    response = client.get(
        SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenarios[0].id)
    )

    assert response.status_code == 200
    assert response.json()["resolved_first_simulation_year"] == 2025


def test_new_hires_plus_baseline_equals_all(env):
    """FR-005 / SC-002: per-year cost invariant across cohorts."""
    client, workspace, scenarios = env
    scenario_id = scenarios[0].id

    def cost_by_year(cohort: str) -> dict[int, float]:
        response = client.get(
            SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenario_id),
            params={"cohort": cohort},
        )
        assert response.status_code == 200
        return {
            row["year"]: row["total_employer_cost"]
            for row in response.json()["contribution_by_year"]
        }

    all_cost = cost_by_year("all")
    new_hire_cost = cost_by_year("new_hires")
    baseline_cost = cost_by_year("baseline")

    for year, total in all_cost.items():
        summed = new_hire_cost.get(year, 0.0) + baseline_cost.get(year, 0.0)
        assert abs(summed - total) < 0.01, f"year {year}: {summed} != {total}"


def test_rates_differ_between_new_hires_and_baseline(env):
    """FR-004: rates are recomputed per-cohort, not sliced from a shared aggregate."""
    client, workspace, scenarios = env
    scenario_id = scenarios[0].id

    def year_2026_row(cohort: str) -> dict:
        response = client.get(
            SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenario_id),
            params={"cohort": cohort},
        )
        assert response.status_code == 200
        rows = {r["year"]: r for r in response.json()["contribution_by_year"]}
        return rows[2026]

    new_hires = year_2026_row("new_hires")
    baseline = year_2026_row("baseline")

    assert new_hires["average_deferral_rate"] != baseline["average_deferral_rate"]
    assert new_hires["employer_cost_rate"] != baseline["employer_cost_rate"]


def test_empty_cohort_is_distinguishable_from_zero_cost(env):
    """FR-012: a cohort with zero eligible employees is distinguishable from a
    cohort with eligible employees but $0 cost.

    `_get_contribution_by_year` is a GROUP BY over filtered rows (matching the
    pre-existing `active_only` behavior) — a year with zero cohort-matching
    employees does not appear in `contribution_by_year` at all, rather than
    appearing with `total_eligible_count == 0`. The frontend empty-state task
    (T024) must therefore detect a *missing* year (reconciled against the
    `cohort=all` year range) as the empty-state trigger, not rely on a present
    row with a zero count.
    """
    client, workspace, scenarios = env
    scenario_id = scenarios[0].id

    response = client.get(
        SINGLE_ENDPOINT.format(workspace_id=workspace.id, scenario_id=scenario_id),
        params={"cohort": "new_hires"},
    )

    assert response.status_code == 200
    rows = {r["year"]: r for r in response.json()["contribution_by_year"]}
    # 2025: no employee hired on/after 2025 yet in the new_hires cohort (e2 hired
    # 2026) — the year is absent entirely, not present with a zero count.
    assert 2025 not in rows
    # 2026: e2 is a genuine new hire with nonzero cost.
    assert rows[2026]["total_eligible_count"] == 1
    assert rows[2026]["total_employer_cost"] > 0.0
