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
