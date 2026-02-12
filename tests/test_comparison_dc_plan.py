"""Tests for DC plan metrics in scenario comparison service."""

from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_api.models.comparison import (
    ComparisonResponse,
    DCPlanComparisonYear,
    DCPlanMetrics,
)
from planalign_api.services.comparison_service import ComparisonService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_snapshot_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create fct_workforce_snapshot table with required columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER,
            employment_status VARCHAR,
            is_enrolled_flag BOOLEAN,
            current_deferral_rate DOUBLE,
            prorated_annual_contributions DOUBLE,
            employer_match_amount DOUBLE,
            employer_core_amount DOUBLE,
            prorated_annual_compensation DOUBLE
        )
    """)


def _create_events_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create fct_yearly_events table (needed by _load_scenario_data)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fct_yearly_events (
            employee_id VARCHAR,
            simulation_year INTEGER,
            event_type VARCHAR
        )
    """)


def _seed_employees(
    conn: duckdb.DuckDBPyConnection,
    rows: list[dict],
) -> None:
    """Insert employee rows into fct_workforce_snapshot."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO fct_workforce_snapshot (
                employee_id, simulation_year, employment_status, is_enrolled_flag,
                current_deferral_rate, prorated_annual_contributions,
                employer_match_amount, employer_core_amount,
                prorated_annual_compensation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["employee_id"],
                row["year"],
                row["status"],
                row["enrolled"],
                row.get("deferral_rate"),
                row.get("contributions"),
                row.get("match"),
                row.get("core"),
                row.get("compensation"),
            ],
        )


def _build_service_with_dbs(
    scenario_db_paths: dict[str, str],
) -> ComparisonService:
    """Build a ComparisonService with a mock resolver mapping scenario IDs to DB paths."""
    mock_storage = MagicMock()
    mock_resolver = MagicMock()

    def _resolve(workspace_id: str, scenario_id: str):
        path = scenario_db_paths.get(scenario_id)
        if path:
            return ResolvedDatabasePath(path=path, source="scenario")
        return ResolvedDatabasePath(path=None, source=None)

    mock_resolver.resolve.side_effect = _resolve
    return ComparisonService(storage=mock_storage, db_resolver=mock_resolver)


def _create_scenario_db(tmp_path, scenario_id: str, rows: list[dict]) -> str:
    """Create a DuckDB file with seeded snapshot data. Returns the path."""
    db_path = str(tmp_path / f"{scenario_id}.duckdb")
    conn = duckdb.connect(db_path)
    _create_snapshot_table(conn)
    _create_events_table(conn)
    _seed_employees(conn, rows)
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Baseline + Alternative test data
# ---------------------------------------------------------------------------

BASELINE_2025 = [
    {"employee_id": "E001", "year": 2025, "status": "Active", "enrolled": True,
     "deferral_rate": 0.06, "contributions": 6000, "match": 3000, "core": 1000,
     "compensation": 100000},
    {"employee_id": "E002", "year": 2025, "status": "Active", "enrolled": True,
     "deferral_rate": 0.04, "contributions": 4000, "match": 2000, "core": 1000,
     "compensation": 100000},
    {"employee_id": "E003", "year": 2025, "status": "Active", "enrolled": False,
     "deferral_rate": None, "contributions": 0, "match": 0, "core": 0,
     "compensation": 100000},
    {"employee_id": "E004", "year": 2025, "status": "Terminated", "enrolled": True,
     "deferral_rate": 0.05, "contributions": 2500, "match": 1250, "core": 500,
     "compensation": 50000},
]

BASELINE_2026 = [
    {"employee_id": "E001", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.07, "contributions": 7000, "match": 3500, "core": 1200,
     "compensation": 105000},
    {"employee_id": "E002", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.05, "contributions": 5000, "match": 2500, "core": 1200,
     "compensation": 105000},
    {"employee_id": "E003", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.03, "contributions": 3000, "match": 1500, "core": 1200,
     "compensation": 105000},
]

ALT_2025 = [
    {"employee_id": "E001", "year": 2025, "status": "Active", "enrolled": True,
     "deferral_rate": 0.08, "contributions": 8000, "match": 5000, "core": 1500,
     "compensation": 100000},
    {"employee_id": "E002", "year": 2025, "status": "Active", "enrolled": True,
     "deferral_rate": 0.06, "contributions": 6000, "match": 4000, "core": 1500,
     "compensation": 100000},
    {"employee_id": "E003", "year": 2025, "status": "Active", "enrolled": True,
     "deferral_rate": 0.04, "contributions": 4000, "match": 2000, "core": 1500,
     "compensation": 100000},
    {"employee_id": "E004", "year": 2025, "status": "Terminated", "enrolled": True,
     "deferral_rate": 0.05, "contributions": 2500, "match": 1250, "core": 750,
     "compensation": 50000},
]

ALT_2026 = [
    {"employee_id": "E001", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.09, "contributions": 9000, "match": 5500, "core": 1500,
     "compensation": 105000},
    {"employee_id": "E002", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.07, "contributions": 7000, "match": 4500, "core": 1500,
     "compensation": 105000},
    {"employee_id": "E003", "year": 2026, "status": "Active", "enrolled": True,
     "deferral_rate": 0.05, "contributions": 5000, "match": 3000, "core": 1500,
     "compensation": 105000},
]


# ---------------------------------------------------------------------------
# Tests: T004 - Happy path
# ---------------------------------------------------------------------------

@pytest.mark.fast
class TestDCPlanMetricsHappyPath:
    """T004: Verify DC plan metrics aggregation across scenarios and years."""

    def test_dc_plan_metrics_happy_path(self, tmp_path):
        """Two scenarios, two years — verify values are returned per year per scenario."""
        baseline_path = _create_scenario_db(
            tmp_path, "baseline", BASELINE_2025 + BASELINE_2026
        )
        alt_path = _create_scenario_db(
            tmp_path, "alternative", ALT_2025 + ALT_2026
        )

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        assert result is not None
        assert len(result.dc_plan_comparison) == 2  # 2 years

        # Year 2025
        year_2025 = result.dc_plan_comparison[0]
        assert year_2025.year == 2025
        assert "baseline" in year_2025.values
        assert "alternative" in year_2025.values

        bl_2025 = year_2025.values["baseline"]
        # Baseline 2025: 3 active, 2 enrolled out of 3 active → 66.67%
        assert abs(bl_2025.participation_rate - 66.67) < 0.1
        # Average deferral among enrolled (all 3 enrolled incl terminated): (0.06 + 0.04 + 0.05) / 3
        # Wait - avg_deferral_rate is for ALL enrolled, not just active enrolled
        assert bl_2025.avg_deferral_rate == pytest.approx(0.05, abs=0.001)
        assert bl_2025.participant_count == 3  # E001, E002, E004
        assert bl_2025.total_employer_match == 6250  # 3000 + 2000 + 1250
        assert bl_2025.total_employer_core == 2500  # 1000 + 1000 + 500
        assert bl_2025.total_employer_cost == 8750
        assert bl_2025.total_employee_contributions == 12500  # 6000 + 4000 + 2500

        alt_2025 = year_2025.values["alternative"]
        # Alt 2025: 3 active, 3 enrolled out of 3 active → 100%
        assert abs(alt_2025.participation_rate - 100.0) < 0.1
        assert alt_2025.participant_count == 4  # all 4 enrolled

        # Year 2026
        year_2026 = result.dc_plan_comparison[1]
        assert year_2026.year == 2026

        bl_2026 = year_2026.values["baseline"]
        # Baseline 2026: 3 active, 3 enrolled → 100%
        assert abs(bl_2026.participation_rate - 100.0) < 0.1
        assert bl_2026.participant_count == 3

    def test_dc_plan_employer_cost_rate(self, tmp_path):
        """Verify employer_cost_rate = total_employer_cost / total_compensation * 100."""
        baseline_path = _create_scenario_db(tmp_path, "baseline", BASELINE_2025)
        alt_path = _create_scenario_db(tmp_path, "alternative", ALT_2025)

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        bl = result.dc_plan_comparison[0].values["baseline"]
        # total_employer_cost = 8750, total_compensation = 350000
        expected_rate = 8750 / 350000 * 100
        assert bl.employer_cost_rate == pytest.approx(expected_rate, abs=0.01)


# ---------------------------------------------------------------------------
# Tests: T005 - Deltas and edge cases
# ---------------------------------------------------------------------------

@pytest.mark.fast
class TestDCPlanDeltas:
    """T005: Verify delta calculations and edge case handling."""

    def test_dc_plan_deltas_vs_baseline(self, tmp_path):
        """Deltas = scenario - baseline; baseline deltas are all zero."""
        baseline_path = _create_scenario_db(
            tmp_path, "baseline", BASELINE_2025
        )
        alt_path = _create_scenario_db(
            tmp_path, "alternative", ALT_2025
        )

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        year_2025 = result.dc_plan_comparison[0]

        # Baseline deltas should all be zero
        bl_delta = year_2025.deltas["baseline"]
        assert bl_delta.participation_rate == 0.0
        assert bl_delta.avg_deferral_rate == 0.0
        assert bl_delta.total_employer_match == 0.0
        assert bl_delta.total_employer_cost == 0.0
        assert bl_delta.participant_count == 0

        # Alternative deltas should be alt - baseline
        alt_delta = year_2025.deltas["alternative"]
        bl_val = year_2025.values["baseline"]
        alt_val = year_2025.values["alternative"]

        assert alt_delta.participation_rate == pytest.approx(
            alt_val.participation_rate - bl_val.participation_rate, abs=0.01
        )
        assert alt_delta.total_employer_match == pytest.approx(
            alt_val.total_employer_match - bl_val.total_employer_match, abs=0.01
        )
        assert alt_delta.total_employer_cost == pytest.approx(
            alt_val.total_employer_cost - bl_val.total_employer_cost, abs=0.01
        )
        assert alt_delta.participant_count == (
            alt_val.participant_count - bl_val.participant_count
        )

    def test_dc_plan_deltas_zero_baseline(self, tmp_path):
        """When baseline has zero employer match, deltas don't error."""
        zero_match_rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": True, "deferral_rate": 0.06, "contributions": 6000,
             "match": 0, "core": 0, "compensation": 100000},
        ]
        alt_rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": True, "deferral_rate": 0.06, "contributions": 6000,
             "match": 3000, "core": 1000, "compensation": 100000},
        ]

        baseline_path = _create_scenario_db(tmp_path, "baseline", zero_match_rows)
        alt_path = _create_scenario_db(tmp_path, "alternative", alt_rows)

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        # Should not error
        assert result is not None
        alt_delta = result.dc_plan_comparison[0].deltas["alternative"]
        assert alt_delta.total_employer_match == 3000.0
        assert alt_delta.total_employer_cost == 4000.0

    def test_dc_plan_zero_enrollment(self, tmp_path):
        """Zero enrolled employees → 0% participation, 0 deferral rate."""
        rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": False, "deferral_rate": None, "contributions": 0,
             "match": 0, "core": 0, "compensation": 100000},
            {"employee_id": "E002", "year": 2025, "status": "Active",
             "enrolled": False, "deferral_rate": None, "contributions": 0,
             "match": 0, "core": 0, "compensation": 100000},
        ]

        bl_path = _create_scenario_db(tmp_path, "baseline", rows)
        alt_path = _create_scenario_db(tmp_path, "alternative", rows)

        service = _build_service_with_dbs({
            "baseline": bl_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        bl = result.dc_plan_comparison[0].values["baseline"]
        assert bl.participation_rate == 0.0
        assert bl.avg_deferral_rate == 0.0
        assert bl.participant_count == 0

    def test_dc_plan_null_contributions(self, tmp_path):
        """NULL contribution columns treated as 0."""
        rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": True, "deferral_rate": 0.06, "contributions": None,
             "match": None, "core": None, "compensation": 100000},
        ]

        bl_path = _create_scenario_db(tmp_path, "baseline", rows)
        alt_path = _create_scenario_db(tmp_path, "alternative", rows)

        service = _build_service_with_dbs({
            "baseline": bl_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        bl = result.dc_plan_comparison[0].values["baseline"]
        assert bl.total_employee_contributions == 0.0
        assert bl.total_employer_match == 0.0
        assert bl.total_employer_core == 0.0
        assert bl.total_employer_cost == 0.0
        assert bl.participation_rate == 100.0  # 1 active, 1 enrolled

    def test_dc_plan_all_terminated(self, tmp_path):
        """All terminated employees → 0% participation, 0 rates."""
        rows = [
            {"employee_id": "E001", "year": 2025, "status": "Terminated",
             "enrolled": True, "deferral_rate": 0.06, "contributions": 6000,
             "match": 3000, "core": 1000, "compensation": 100000},
        ]

        bl_path = _create_scenario_db(tmp_path, "baseline", rows)
        alt_path = _create_scenario_db(tmp_path, "alternative", rows)

        service = _build_service_with_dbs({
            "baseline": bl_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        bl = result.dc_plan_comparison[0].values["baseline"]
        assert bl.participation_rate == 0.0  # No active employees
        # Contributions still counted (full-year contributions for terminated)
        assert bl.total_employee_contributions == 6000.0


# ---------------------------------------------------------------------------
# Tests: T009 - Summary deltas
# ---------------------------------------------------------------------------

@pytest.mark.fast
class TestDCPlanSummaryDeltas:
    """T009: Verify summary_deltas includes DC plan metrics."""

    def test_dc_plan_summary_deltas(self, tmp_path):
        """summary_deltas includes final_participation_rate and final_employer_cost."""
        baseline_path = _create_scenario_db(
            tmp_path, "baseline", BASELINE_2025 + BASELINE_2026
        )
        alt_path = _create_scenario_db(
            tmp_path, "alternative", ALT_2025 + ALT_2026
        )

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        # Keys exist
        assert "final_participation_rate" in result.summary_deltas
        assert "final_employer_cost" in result.summary_deltas

        # Baseline values match final year (2026)
        final_year = result.dc_plan_comparison[-1]
        bl_final = final_year.values["baseline"]

        pr_delta = result.summary_deltas["final_participation_rate"]
        assert pr_delta.baseline == bl_final.participation_rate

        ec_delta = result.summary_deltas["final_employer_cost"]
        assert ec_delta.baseline == bl_final.total_employer_cost

        # Deltas computed correctly for alternative
        alt_final = final_year.values["alternative"]
        assert pr_delta.deltas["alternative"] == pytest.approx(
            alt_final.participation_rate - bl_final.participation_rate, abs=0.01
        )
        assert ec_delta.deltas["alternative"] == pytest.approx(
            alt_final.total_employer_cost - bl_final.total_employer_cost, abs=0.01
        )

        # Baseline deltas are zero
        assert pr_delta.deltas["baseline"] == 0.0
        assert ec_delta.deltas["baseline"] == 0.0

    def test_dc_plan_summary_single_year(self, tmp_path):
        """Single-year comparison: summary values match the only year's values."""
        baseline_path = _create_scenario_db(tmp_path, "baseline", BASELINE_2025)
        alt_path = _create_scenario_db(tmp_path, "alternative", ALT_2025)

        service = _build_service_with_dbs({
            "baseline": baseline_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        assert len(result.dc_plan_comparison) == 1
        only_year = result.dc_plan_comparison[0]

        pr_delta = result.summary_deltas["final_participation_rate"]
        assert pr_delta.baseline == only_year.values["baseline"].participation_rate

        ec_delta = result.summary_deltas["final_employer_cost"]
        assert ec_delta.baseline == only_year.values["baseline"].total_employer_cost

    def test_dc_plan_summary_zero_baseline(self, tmp_path):
        """Zero baseline employer cost → delta_pcts = 0% (no division by zero)."""
        zero_cost_rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": True, "deferral_rate": 0.06, "contributions": 6000,
             "match": 0, "core": 0, "compensation": 100000},
        ]
        alt_rows = [
            {"employee_id": "E001", "year": 2025, "status": "Active",
             "enrolled": True, "deferral_rate": 0.06, "contributions": 6000,
             "match": 3000, "core": 1000, "compensation": 100000},
        ]

        bl_path = _create_scenario_db(tmp_path, "baseline", zero_cost_rows)
        alt_path = _create_scenario_db(tmp_path, "alternative", alt_rows)

        service = _build_service_with_dbs({
            "baseline": bl_path,
            "alternative": alt_path,
        })

        result = service.compare_scenarios(
            workspace_id="ws1",
            scenario_ids=["baseline", "alternative"],
            baseline_id="baseline",
        )

        ec_delta = result.summary_deltas["final_employer_cost"]
        assert ec_delta.baseline == 0.0
        assert ec_delta.delta_pcts["alternative"] == 0.0  # No division by zero
