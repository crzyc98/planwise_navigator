"""API contract tests for DC Plan cohort and eligible-population parameters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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
        conn.execute("""
            CREATE TABLE config_irs_limits (
                limit_year INTEGER,
                compensation_limit DECIMAL(12, 2)
            );
            INSERT INTO config_irs_limits VALUES
                (2025, 350000),
                (2026, 350000)
            """)
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
        assert rows[2025]["total_capped_compensation"] == 100000.0
        assert rows[2025]["employer_cost_pct_of_capped_compensation"] == 2.0
        assert analytics["total_capped_compensation"] == 280000.0
        assert analytics["employer_cost_pct_of_capped_compensation"] == 1.89


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


# Issue #970: the final-year deferral distribution is derived from the
# all-years query. These rows make the two rate modes bucket differently, add a
# terminated-in-final-year row, a NULL current rate, and a 2025-only new-hire
# termination so `terminated_eligible` + `new_hires` has rows only before the
# final year.
DEFERRAL_PARITY_ROWS = """
    INSERT INTO fct_workforce_snapshot (
        employee_id, simulation_year, employment_status, termination_date,
        employee_hire_date, current_eligibility_status, is_enrolled_flag,
        current_deferral_rate, effective_annual_deferral_rate
    ) VALUES
        ('e4', 2026, 'TERMINATED', DATE '2026-05-01', DATE '2021-01-01', 'eligible', true, 0, 0.04),
        ('e5', 2026, 'ACTIVE', NULL, DATE '2026-02-01', 'eligible', true, 0.12, 0.09),
        ('e6', 2026, 'ACTIVE', NULL, DATE '2023-01-01', 'eligible', true, NULL, 0.015),
        ('e7', 2025, 'TERMINATED', DATE '2025-09-01', DATE '2025-02-01', 'eligible', true, 0.03, 0.01)
"""

DEFERRAL_FILTERS = [
    (False, None),
    (True, None),
    (False, "all_eligible"),
    (False, "active_eligible"),
    (False, "terminated_eligible"),
]


def _legacy_final_year_counts(
    conn: duckdb.DuckDBPyConnection,
    effective_rate: bool,
    active_only: bool,
    population: str | None,
    cohort: str,
) -> dict[str, int]:
    """Pre-#970 dedicated final-year query, kept verbatim as the parity oracle."""
    service = AnalyticsService
    rate_col = (
        "effective_annual_deferral_rate" if effective_rate else "current_deferral_rate"
    )
    status_filter = ""
    if population is None and (active_only or not effective_rate):
        status_filter = "UPPER(employment_status) = 'ACTIVE'"
    where_clause = service._combine_where(
        "simulation_year = final_year.max_year",
        status_filter,
        service._population_predicate(population),
        service._cohort_predicate(cohort, 2025),
    )
    rows = conn.execute(f"""
        WITH final_year AS (
            SELECT MAX(simulation_year) as max_year FROM fct_workforce_snapshot
        ),
        bucketed AS (
            SELECT
                CASE
                    WHEN {rate_col} IS NULL OR {rate_col} = 0 THEN '0%'
                    WHEN {rate_col} < 0.015 THEN '1%'
                    WHEN {rate_col} < 0.025 THEN '2%'
                    WHEN {rate_col} < 0.035 THEN '3%'
                    WHEN {rate_col} < 0.045 THEN '4%'
                    WHEN {rate_col} < 0.055 THEN '5%'
                    WHEN {rate_col} < 0.065 THEN '6%'
                    WHEN {rate_col} < 0.075 THEN '7%'
                    WHEN {rate_col} < 0.085 THEN '8%'
                    WHEN {rate_col} < 0.095 THEN '9%'
                    ELSE '10%+'
                END as bucket
            FROM fct_workforce_snapshot, final_year
            {where_clause}
        )
        SELECT bucket, COUNT(*) as count FROM bucketed GROUP BY bucket
        """).fetchall()
    return {str(bucket): int(count) for bucket, count in rows}


@pytest.fixture
def deferral_conn(tmp_path):
    path = _build_db(tmp_path / "deferral.duckdb")
    conn = duckdb.connect(str(path))
    conn.execute(DEFERRAL_PARITY_ROWS)
    yield conn
    conn.close()


@pytest.mark.parametrize("cohort", ["all", "new_hires", "baseline"])
@pytest.mark.parametrize(("active_only", "population"), DEFERRAL_FILTERS)
@pytest.mark.parametrize("effective_rate", [False, True])
def test_derived_final_year_deferral_matches_legacy_query(
    deferral_conn, effective_rate, active_only, population, cohort
):
    service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
    final, by_year = service._get_deferral_distributions(
        deferral_conn,
        effective_rate=effective_rate,
        active_only=active_only,
        population=population,
        cohort=cohort,
        first_simulation_year=2025,
    )
    expected = service._deferral_buckets(
        _legacy_final_year_counts(
            deferral_conn, effective_rate, active_only, population, cohort
        )
    )

    assert final == expected
    assert [b.bucket for b in final] == list(
        "0% 1% 2% 3% 4% 5% 6% 7% 8% 9% 10%+".split()
    )
    if by_year and by_year[-1].year == 2026:
        assert by_year[-1].distribution == final


def test_final_year_is_snapshot_max_not_latest_nonempty_year(deferral_conn):
    """A filter that empties the final year yields zero buckets, never 2025's."""
    service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())
    final, by_year = service._get_deferral_distributions(
        deferral_conn,
        effective_rate=True,
        population="terminated_eligible",
        cohort="new_hires",
        first_simulation_year=2025,
    )

    assert [year.year for year in by_year] == [2025]
    assert sum(b.count for b in by_year[0].distribution) == 1
    assert all(b.count == 0 and b.percentage == 0.0 for b in final)
    assert len(final) == 11


def test_deferral_distributions_use_one_query(deferral_conn):
    spy = MagicMock(wraps=deferral_conn)
    service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())

    service._get_deferral_distributions(spy, effective_rate=True)

    assert spy.execute.call_count == 1


def test_empty_snapshot_yields_zero_buckets_and_no_years(tmp_path):
    conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
    conn.execute(SNAPSHOT_DDL)
    service = AnalyticsService(storage=MagicMock(), db_resolver=MagicMock())

    final, by_year = service._get_deferral_distributions(conn)
    conn.close()

    assert by_year == []
    assert [(b.count, b.percentage) for b in final] == [(0, 0.0)] * 11


@pytest.mark.parametrize("effective_rate", ["false", "true"])
def test_api_final_year_distribution_matches_last_year(env, effective_rate):
    client, workspace, scenarios = env
    endpoint = SINGLE_ENDPOINT.format(
        workspace_id=workspace.id, scenario_id=scenarios[0].id
    )

    body = client.get(endpoint, params={"effective_rate": effective_rate}).json()
    assert body["deferral_distribution_by_year"][-1]["year"] == 2026
    assert (
        body["deferral_rate_distribution"]
        == body["deferral_distribution_by_year"][-1]["distribution"]
    )

    terms = client.get(
        endpoint,
        params={"effective_rate": effective_rate, "population": "terminated_eligible"},
    ).json()
    assert [y["year"] for y in terms["deferral_distribution_by_year"]] == [2025]
    assert all(b["count"] == 0 for b in terms["deferral_rate_distribution"])
