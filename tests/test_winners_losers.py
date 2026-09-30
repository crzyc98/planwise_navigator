"""Tests for Winners & Losers comparison service."""

import pandas as pd
import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from planalign_api.routers import analytics
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.winners_losers_service import (
    ComparisonEvidenceChangedError,
    IncompatibleSimulationYearsError,
    WinnersLosersService,
)


@pytest.fixture
def scenario_service(tmp_path):
    """Create two disposable databases with deliberately changing contributions."""

    def create(years_a, years_b):
        paths = {}
        for scenario_id, years in [("a", years_a), ("b", years_b)]:
            path = tmp_path / f"{scenario_id}.duckdb"
            with duckdb.connect(str(path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE fct_workforce_snapshot (
                        employee_id VARCHAR, simulation_year INTEGER,
                        employment_status VARCHAR, age_band VARCHAR,
                        tenure_band VARCHAR, employer_match_amount DOUBLE,
                        employer_core_amount DOUBLE
                    )
                """
                )
                for year in years:
                    # Same-year B loses; comparing an earlier A to a later B wins.
                    amount = (
                        1000 + (year - 2025) * 500 - (100 if scenario_id == "b" else 0)
                    )
                    conn.execute(
                        "INSERT INTO fct_workforce_snapshot VALUES "
                        "('SYNTHETIC', ?, 'active', '25-34', '< 2', ?, 0)",
                        [year, amount],
                    )
            paths[scenario_id] = ResolvedDatabasePath(path=path, source="scenario")
        resolver = Mock()
        resolver.resolve.side_effect = lambda workspace_id, scenario_id: paths[
            scenario_id
        ]
        storage = Mock()
        storage.get_scenario.return_value.status = "completed"
        return WinnersLosersService(storage, resolver)

    return create


@pytest.mark.parametrize(
    "years_a,years_b,expected_year",
    [
        ([2025, 2026], [2025, 2026], 2026),
        ([2025, 2026], [2026, 2027], 2026),
        ([2026, 2027], [2025, 2026], 2026),
        ([2025, 2027], [2025, 2026], 2025),
    ],
)
@pytest.mark.parametrize("via_api", [False, True])
def test_latest_common_year(
    scenario_service, monkeypatch, years_a, years_b, expected_year, via_api
):
    service = scenario_service(years_a, years_b)
    if via_api:
        response = _api_client(service, monkeypatch).get(
            "/ws/analytics/winners-losers", params={"plan_a": "a", "plan_b": "b"}
        )
        assert response.status_code == 200
        result = response.json()
    else:
        result = service.analyze("ws", "a", "b").model_dump()
    assert result["final_year"] == expected_year
    assert result["plan_a_final_year"] == max(years_a)
    assert result["plan_b_final_year"] == max(years_b)
    assert result["total_compared"] == 1
    assert result["total_losers"] == 1
    assert result["total_winners"] == result["total_neutral"] == 0
    assert result["total_excluded"] == 0


def _api_client(service, monkeypatch):
    app = FastAPI()
    app.include_router(analytics.router)
    app.dependency_overrides[analytics.get_storage] = lambda: service.storage
    app.dependency_overrides[analytics.get_winners_losers_service] = lambda: service
    monkeypatch.setattr(analytics, "has_selected_result", lambda *args: True)
    return TestClient(app)


def test_disjoint_years_rejected(scenario_service, monkeypatch):
    service = scenario_service([2025], [2027])
    with pytest.raises(
        IncompatibleSimulationYearsError, match="no common simulation year"
    ):
        service.analyze("ws", "a", "b")
    response = _api_client(service, monkeypatch).get(
        "/ws/analytics/winners-losers", params={"plan_a": "a", "plan_b": "b"}
    )
    assert response.status_code == 422
    assert "no common simulation year" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------


class TestClassifyEmployees:
    """Test _classify_employees static method."""

    def test_basic_classification(self):
        df_a = pd.DataFrame(
            {
                "employee_id": ["E1", "E2", "E3"],
                "age_band": ["25-34", "35-44", "25-34"],
                "tenure_band": ["< 2", "2-4", "< 2"],
                "employer_total": [1000.0, 2000.0, 1500.0],
            }
        )
        df_b = pd.DataFrame(
            {
                "employee_id": ["E1", "E2", "E3"],
                "employer_total": [1500.0, 1500.0, 1500.0],
            }
        )

        merged, excluded = WinnersLosersService._classify_employees(df_a, df_b)

        assert len(merged) == 3
        assert excluded == 0

        e1 = merged[merged["employee_id"] == "E1"].iloc[0]
        assert e1["status"] == "winner"
        assert e1["delta"] == 500.0

        e2 = merged[merged["employee_id"] == "E2"].iloc[0]
        assert e2["status"] == "loser"
        assert e2["delta"] == -500.0

        e3 = merged[merged["employee_id"] == "E3"].iloc[0]
        assert e3["status"] == "neutral"
        assert e3["delta"] == 0.0

    def test_excluded_employees(self):
        df_a = pd.DataFrame(
            {
                "employee_id": ["E1", "E2"],
                "age_band": ["25-34", "35-44"],
                "tenure_band": ["< 2", "2-4"],
                "employer_total": [1000.0, 2000.0],
            }
        )
        df_b = pd.DataFrame(
            {
                "employee_id": ["E2", "E3"],
                "employer_total": [2500.0, 3000.0],
            }
        )

        merged, excluded = WinnersLosersService._classify_employees(df_a, df_b)

        assert len(merged) == 1  # Only E2 in both
        assert excluded == 2  # E1 and E3 excluded
        assert merged.iloc[0]["employee_id"] == "E2"
        assert merged.iloc[0]["status"] == "winner"

    def test_empty_dataframes(self):
        df_a = pd.DataFrame(
            columns=["employee_id", "age_band", "tenure_band", "employer_total"]
        )
        df_b = pd.DataFrame(columns=["employee_id", "employer_total"])

        merged, excluded = WinnersLosersService._classify_employees(df_a, df_b)

        assert len(merged) == 0
        assert excluded == 0


# ---------------------------------------------------------------------------
# Aggregation tests
# ---------------------------------------------------------------------------


class TestAggregateResults:
    """Test _aggregate_results static method."""

    def _make_merged(self):
        return pd.DataFrame(
            {
                "employee_id": ["E1", "E2", "E3", "E4"],
                "age_band": ["25-34", "25-34", "35-44", "35-44"],
                "tenure_band": ["< 2", "2-4", "< 2", "2-4"],
                "employer_total_a": [1000, 2000, 1500, 1800],
                "employer_total_b": [1500, 1800, 1500, 2000],
                "delta": [500, -200, 0, 200],
                "status": ["winner", "loser", "neutral", "winner"],
            }
        )

    def test_age_band_aggregation(self):
        merged = self._make_merged()
        age_results, _, _ = WinnersLosersService._aggregate_results(merged)

        assert len(age_results) == 2
        band_25 = next(r for r in age_results if r.band_label == "25-34")
        assert band_25.winners == 1
        assert band_25.losers == 1
        assert band_25.neutral == 0
        assert band_25.total == 2

        band_35 = next(r for r in age_results if r.band_label == "35-44")
        assert band_35.winners == 1
        assert band_35.losers == 0
        assert band_35.neutral == 1
        assert band_35.total == 2

    def test_tenure_band_aggregation(self):
        merged = self._make_merged()
        _, tenure_results, _ = WinnersLosersService._aggregate_results(merged)

        assert len(tenure_results) == 2
        band_lt2 = next(r for r in tenure_results if r.band_label == "< 2")
        assert band_lt2.winners == 1
        assert band_lt2.neutral == 1
        assert band_lt2.total == 2

    def test_heatmap_aggregation(self):
        merged = self._make_merged()
        _, _, heatmap = WinnersLosersService._aggregate_results(merged)

        assert len(heatmap) == 4  # 2 age × 2 tenure
        cell = next(
            c for c in heatmap if c.age_band == "25-34" and c.tenure_band == "< 2"
        )
        assert cell.winners == 1
        assert cell.losers == 0
        assert cell.total == 1
        assert cell.net_pct == 100.0

    def test_empty_merged(self):
        merged = pd.DataFrame(
            columns=[
                "employee_id",
                "age_band",
                "tenure_band",
                "employer_total_a",
                "employer_total_b",
                "delta",
                "status",
            ]
        )
        age, tenure, heatmap = WinnersLosersService._aggregate_results(merged)
        assert age == []
        assert tenure == []
        assert heatmap == []

    def test_totals_consistent(self):
        merged = self._make_merged()
        age_results, tenure_results, heatmap = WinnersLosersService._aggregate_results(
            merged
        )

        age_total = sum(r.total for r in age_results)
        tenure_total = sum(r.total for r in tenure_results)
        heatmap_total = sum(c.total for c in heatmap)

        assert age_total == tenure_total == heatmap_total == 4


@pytest.fixture
def dollar_service(scenario_service):
    service = scenario_service([2025, 2026], [2025, 2026])
    rows = {
        "a": [
            ("E1", "25-34", "< 2", 100.005),
            ("E2", "25-34", "2-4", 1000),
            ("E3", None, None, 300),
            ("ONLY_A", "35-44", "< 2", 9000),
        ],
        "b": [
            ("E1", "25-34", "< 2", 5100.005),
            ("E2", "25-34", "2-4", 999),
            ("E3", None, None, 300.004),
            ("ONLY_B", "35-44", "< 2", 8000),
        ],
    }
    for scenario, employees in rows.items():
        resolved = service.db_resolver.resolve("ws", scenario)
        with duckdb.connect(str(resolved.path)) as conn:
            conn.execute(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = 2026"
            )
            conn.executemany(
                "INSERT INTO fct_workforce_snapshot VALUES (?, 2026, 'active', ?, ?, ?, 0)",
                employees,
            )
            conn.execute(
                "INSERT INTO fct_workforce_snapshot VALUES ('INACTIVE', 2026, 'terminated', '25-34', '< 2', 99999, 0)"
            )
            if scenario == "a":
                conn.execute(
                    "UPDATE fct_workforce_snapshot SET employer_core_amount = employer_match_amount, employer_match_amount = NULL WHERE employee_id = 'E1'"
                )
            else:
                conn.execute(
                    "UPDATE fct_workforce_snapshot SET employer_core_amount = NULL WHERE employee_id = 'E1'"
                )
    return service


def test_dollar_totals_reconcile_and_reverse(dollar_service):
    result = dollar_service.analyze("ws", "a", "b")
    page = dollar_service.employee_impacts("ws", "a", "b", 2026)
    assert result.total_compared == 3
    assert result.total_excluded == 2
    assert (result.total_winners, result.total_losers, result.total_neutral) == (
        1,
        1,
        1,
    )
    assert result.total_increases == 5000
    assert result.total_decreases == -1
    assert result.net_contribution_change == 4999
    assert result.average_change == 1666.33
    assert page.employees[0].plan_a_amount == 100.01
    assert page.employees[0].plan_b_amount == 5100.01
    assert (
        sum(employee.delta for employee in page.employees)
        == result.net_contribution_change
    )
    for bands in (result.age_band_results, result.tenure_band_results, result.heatmap):
        assert sum(band.total for band in bands) == result.total_compared
        for field in ("total_increases", "total_decreases", "net_contribution_change"):
            assert sum(getattr(band, field) for band in bands) == getattr(result, field)
    reverse = dollar_service.analyze("ws", "b", "a")
    assert reverse.total_winners == result.total_losers
    assert reverse.total_losers == result.total_winners
    assert reverse.total_neutral == result.total_neutral
    assert reverse.net_contribution_change == -result.net_contribution_change
    assert reverse.total_increases == -result.total_decreases
    assert reverse.total_decreases == -result.total_increases
    assert reverse.average_change == -result.average_change


def test_detail_filters_pagination_and_contract(dollar_service, monkeypatch):
    client = _api_client(dollar_service, monkeypatch)
    params = {
        "plan_a": "a",
        "plan_b": "b",
        "comparison_year": 2026,
        "age_band": "25-34",
        "limit": 1,
    }
    first = client.get("/ws/analytics/winners-losers/employees", params=params)
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 2
    assert body["net_contribution_change"] == 4999
    assert body["final_year"] == 2026
    assert body["plan_a_run_id"] is body["plan_b_run_id"] is None
    assert body["employees"][0]["employee_id"] == "E1"
    assert set(body["employees"][0]) == {
        "employee_id",
        "age_band",
        "tenure_band",
        "plan_a_amount",
        "plan_b_amount",
        "delta",
        "status",
    }
    params["offset"] = 1
    second = client.get("/ws/analytics/winners-losers/employees", params=params).json()
    assert second["employees"][0]["employee_id"] == "E2"
    assert second["net_contribution_change"] == body["net_contribution_change"]
    params.update(offset=0, tenure_band="2-4")
    cell = client.get("/ws/analytics/winners-losers/employees", params=params).json()
    assert cell["total"] == 1
    assert cell["total_decreases"] == -1
    params.update(age_band="Unknown", tenure_band="Unknown")
    unknown = client.get("/ws/analytics/winners-losers/employees", params=params).json()
    assert unknown["total"] == 1
    assert unknown["employees"][0]["status"] == "neutral"
    params["age_band"] = "No such band"
    empty = client.get("/ws/analytics/winners-losers/employees", params=params).json()
    assert empty["total"] == 0
    assert empty["average_change"] == empty["net_contribution_change"] == 0
    assert empty["employees"] == []


@pytest.mark.parametrize(
    "overrides",
    [{"limit": 101}, {"limit": 0}, {"offset": -1}, {"comparison_year": "bad"}],
)
def test_detail_query_validation(scenario_service, monkeypatch, overrides):
    service = scenario_service([2026], [2026])
    params = {"plan_a": "a", "plan_b": "b", "comparison_year": 2026, **overrides}
    assert (
        _api_client(service, monkeypatch)
        .get("/ws/analytics/winners-losers/employees", params=params)
        .status_code
        == 422
    )


def test_detail_pins_selected_run_and_year(scenario_service, monkeypatch):
    service = scenario_service([2026], [2026])
    paths = {
        sid: service.db_resolver.resolve("ws", sid).model_copy(
            update={"run_id": f"run-{sid}"}
        )
        for sid in ("a", "b")
    }
    service.db_resolver.resolve.side_effect = lambda ws, sid: paths[sid]
    summary = service.analyze("ws", "a", "b")
    assert summary.plan_a_run_id == "run-a"
    assert summary.plan_b_run_id == "run-b"
    page = service.employee_impacts("ws", "a", "b", 2026, "run-a", "run-b")
    assert page.plan_a_run_id == "run-a"
    paths["b"] = paths["b"].model_copy(update={"run_id": "new-b"})
    with pytest.raises(ComparisonEvidenceChangedError, match="Selected runs changed"):
        service.employee_impacts("ws", "a", "b", 2026, "run-a", "run-b")
    client = _api_client(service, monkeypatch)
    assert (
        client.get(
            "/ws/analytics/winners-losers/employees",
            params={
                "plan_a": "a",
                "plan_b": "b",
                "comparison_year": 2026,
                "plan_a_run_id": "run-a",
                "plan_b_run_id": "run-b",
            },
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/ws/analytics/winners-losers/employees",
            params={
                "plan_a": "a",
                "plan_b": "b",
                "comparison_year": 2025,
                "plan_a_run_id": "run-a",
                "plan_b_run_id": "new-b",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "empty_scenarios,compared,excluded",
    [((), 0, 2), (("a",), 0, 1), (("a", "b"), 0, 0)],
)
def test_empty_and_disjoint_populations(
    scenario_service, empty_scenarios, compared, excluded
):
    service = scenario_service([2026], [2026])
    for sid in ("a", "b"):
        with duckdb.connect(str(service.db_resolver.resolve("ws", sid).path)) as conn:
            if sid in empty_scenarios:
                conn.execute(
                    "UPDATE fct_workforce_snapshot SET employment_status = 'terminated'"
                )
            else:
                conn.execute("UPDATE fct_workforce_snapshot SET employee_id = ?", [sid])
    result = service.analyze("ws", "a", "b")
    assert result.total_compared == compared
    assert result.total_excluded == excluded
    assert (
        result.total_increases
        == result.total_decreases
        == result.net_contribution_change
        == result.average_change
        == 0
    )
    assert service.employee_impacts("ws", "a", "b", 2026).employees == []


def test_duplicate_employee_grain_fails(scenario_service):
    service = scenario_service([2026], [2026])
    with duckdb.connect(str(service.db_resolver.resolve("ws", "a").path)) as conn:
        conn.execute(
            "INSERT INTO fct_workforce_snapshot SELECT * FROM fct_workforce_snapshot"
        )
    assert service.analyze("ws", "a", "b") is None
