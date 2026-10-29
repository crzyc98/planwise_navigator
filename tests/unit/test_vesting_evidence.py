"""Independent financial controls for vesting history scope and integrity."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from planalign_api.models.vesting import VestingScheduleConfig, VestingScheduleType
from planalign_api.services.vesting_service import (
    VestingService,
    project_forfeitures_for_connection,
)
from planalign_api.services.vesting_evidence import VestingEvidenceError
from planalign_api.services.database_path_resolver import ResolvedDatabasePath

SCHEDULE = VestingScheduleConfig(
    schedule_type=VestingScheduleType.CLIFF_3_YEAR, name="Cliff3"
)


def populate(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""CREATE TABLE fct_workforce_snapshot (
        scenario_id VARCHAR, plan_design_id VARCHAR, employee_id VARCHAR,
        simulation_year INTEGER, employment_status VARCHAR, current_tenure INTEGER,
        tenure_band VARCHAR, annual_hours_worked INTEGER, total_employer_contributions DOUBLE,
        employee_hire_date DATE, termination_date DATE)""")
    for design, amount in (("A", 100), ("B", 300)):
        conn.execute(
            """INSERT INTO fct_workforce_snapshot VALUES
        ('S', ?, 'E', 2025, 'ACTIVE', 0, '<2', 2080, ?, '2025-01-01', NULL),
        ('S', ?, 'E', 2026, 'TERMINATED', 1, '<2', 1040, 0, '2025-01-01', '2026-06-30'),
        ('S', ?, 'X', 2027, 'ACTIVE', 0, '<2', 2080, 0, '2027-01-01', NULL)
        """,
            [design, amount, design, design],
        )


def test_design_population_and_single_year_basis_are_not_multiplied() -> None:
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        for where, expected, count in [
            ("", 400, 2),
            ("WHERE plan_design_id='A'", 100, 1),
            ("WHERE plan_design_id='B'", 300, 1),
        ]:
            row = project_forfeitures_for_connection(conn, SCHEDULE, where)[1]
            assert row.total_employer_contributions == Decimal(expected)
            assert row.forfeited_amount == Decimal(expected)
            assert row.vesting_eligible_count == count
        details = VestingService(Mock())._get_terminated_employees(conn, 2026)
        assert {row["plan_design_id"] for row in details} == {"A", "B"}
        assert {row["configured_scenario_id"] for row in details} == {"S"}
        assert sorted(row["total_employer_contributions"] for row in details) == [
            100,
            300,
        ]


@pytest.mark.parametrize("invalid", [None, -500, float("nan"), float("inf")])
def test_invalid_used_history_does_not_become_a_zero_offset(
    invalid: float | None,
) -> None:
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        conn.execute(
            "UPDATE fct_workforce_snapshot SET total_employer_contributions=? WHERE plan_design_id='B' AND simulation_year=2025",
            [invalid],
        )
        # An unrelated design's bad row does not invalidate A's selected history.
        assert (
            project_forfeitures_for_connection(
                conn, SCHEDULE, "WHERE plan_design_id='A'"
            )[1].forfeited_amount
            == 100
        )
        with pytest.raises(VestingEvidenceError, match="invalid prior"):
            project_forfeitures_for_connection(conn, SCHEDULE)
        with pytest.raises(VestingEvidenceError, match="invalid prior"):
            VestingService(Mock())._get_terminated_employees(conn, 2026)


def test_duplicate_selected_history_is_rejected_but_distinct_scenarios_are_not() -> (
    None
):
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        conn.execute(
            "INSERT INTO fct_workforce_snapshot SELECT * REPLACE ('T' AS scenario_id) FROM fct_workforce_snapshot"
        )
        assert (
            project_forfeitures_for_connection(conn, SCHEDULE)[1].forfeited_amount
            == 800
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot SELECT * FROM fct_workforce_snapshot WHERE scenario_id='S' AND plan_design_id='A' AND simulation_year=2025"
        )
        with pytest.raises(VestingEvidenceError, match="duplicate"):
            project_forfeitures_for_connection(conn, SCHEDULE)
        assert (
            project_forfeitures_for_connection(conn, SCHEDULE, "WHERE scenario_id='T'")[
                1
            ].forfeited_amount
            == 400
        )


def test_public_projection_discloses_skipped_invalid_scenario(tmp_path: Path) -> None:
    path = tmp_path / "invalid.duckdb"
    with duckdb.connect(str(path)) as conn:
        populate(conn)
        conn.execute(
            "UPDATE fct_workforce_snapshot SET total_employer_contributions=NULL WHERE simulation_year=2025"
        )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    result = VestingService(Mock(), resolver).project_forfeitures(
        "w", [("s", "Synthetic")], SCHEDULE
    )
    assert result.scenarios == []
    assert len(result.skipped) == 1
    assert "invalid prior" in result.skipped[0].reason
    with duckdb.connect(str(path), read_only=True) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()[0]
            == 6
        )


def test_analysis_route_returns_evidence_error_as_422() -> None:
    from fastapi import HTTPException
    from planalign_api.models.vesting import VestingAnalysisRequest
    from planalign_api.routers.vesting import analyze_vesting

    service = Mock()
    service.storage.get_scenario.return_value.name = "Synthetic"
    service.analyze_vesting.side_effect = VestingEvidenceError("invalid prior basis")
    request = VestingAnalysisRequest(
        current_schedule=SCHEDULE, proposed_schedule=SCHEDULE
    )
    with pytest.raises(HTTPException) as caught:
        analyze_vesting("w", "s", request, vesting_service=service)
    assert caught.value.status_code == 422
    assert caught.value.detail == "invalid prior basis"


def test_cost_comparison_route_returns_evidence_error_as_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from planalign_api.routers import analytics
    from planalign_api.models.employer_cost import ForfeiturePolicy

    monkeypatch.setattr(analytics, "has_selected_result", lambda *args: True)
    storage = Mock()
    storage.get_scenario.return_value.name = "Synthetic"
    service = Mock()
    service.get_grandfathered_cost_comparison.side_effect = VestingEvidenceError(
        "invalid prior basis"
    )
    with pytest.raises(HTTPException) as caught:
        analytics.compare_grandfathered_cost(
            "w",
            baseline_scenario="s",
            scenarios="s",
            cutoff_year=2025,
            schedule_type=VestingScheduleType.CLIFF_3_YEAR,
            forfeiture_policy=ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
            storage=storage,
            analytics_service=service,
        )
    assert caught.value.status_code == 422
    assert caught.value.detail == "invalid prior basis"


@pytest.mark.parametrize("column", ["scenario_id", "plan_design_id"])
def test_null_scope_in_prior_history_is_evidence_error(column: str) -> None:
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        conn.execute(
            f"UPDATE fct_workforce_snapshot SET {column}=NULL "
            "WHERE plan_design_id='A' AND simulation_year=2025"
        )
        with pytest.raises(VestingEvidenceError, match="missing snapshot identity"):
            project_forfeitures_for_connection(conn, SCHEDULE)
        with pytest.raises(VestingEvidenceError, match="missing snapshot identity"):
            VestingService(Mock())._get_terminated_employees(conn, 2026)


@pytest.mark.parametrize("status", ["ACTIVE", "TERMINATED"])
def test_null_year_in_selected_history_is_evidence_error(status: str) -> None:
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        conn.execute(
            "UPDATE fct_workforce_snapshot SET simulation_year=NULL "
            "WHERE plan_design_id='B' AND employee_id='E' AND employment_status=?",
            [status],
        )
        with pytest.raises(VestingEvidenceError, match="missing snapshot identity"):
            project_forfeitures_for_connection(conn, SCHEDULE)
        rows = project_forfeitures_for_connection(
            conn, SCHEDULE, "WHERE plan_design_id='A'"
        )
        assert [row.simulation_year for row in rows] == [2025, 2026, 2027]
        assert rows[1].forfeited_amount == 100


@pytest.mark.parametrize(
    "column,value,require_hours",
    [
        ("current_tenure", -1, False),
        ("current_tenure", None, False),
        ("annual_hours_worked", None, True),
        ("annual_hours_worked", -1, True),
    ],
)
def test_invalid_consumed_service_credit_is_unavailable(
    column: str, value: int | None, require_hours: bool
) -> None:
    with duckdb.connect(":memory:") as conn:
        populate(conn)
        conn.execute(
            f"UPDATE fct_workforce_snapshot SET {column}=? WHERE employment_status='TERMINATED'",
            [value],
        )
        schedule = SCHEDULE.model_copy(update={"require_hours_credit": require_hours})
        with pytest.raises(VestingEvidenceError):
            project_forfeitures_for_connection(conn, schedule)


@pytest.mark.parametrize("hours", [None, -1])
@pytest.mark.parametrize("required_side", [None, "current", "proposed"])
def test_public_analysis_preserves_unknown_unused_hours(
    tmp_path: Path, hours: int | None, required_side: str | None
) -> None:
    from planalign_api.models.vesting import VestingAnalysisRequest

    path = tmp_path / "hours.duckdb"
    with duckdb.connect(str(path)) as conn:
        populate(conn)
        conn.execute(
            "UPDATE fct_workforce_snapshot SET current_tenure=3, annual_hours_worked=? WHERE employment_status='TERMINATED'",
            [hours],
        )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    service = VestingService(Mock(), resolver)
    request = VestingAnalysisRequest(
        current_schedule=SCHEDULE.model_copy(
            update={"require_hours_credit": required_side == "current"}
        ),
        proposed_schedule=SCHEDULE.model_copy(
            update={"require_hours_credit": required_side == "proposed"}
        ),
        simulation_year=2026,
    )
    if required_side:
        with pytest.raises(VestingEvidenceError, match="invalid hours"):
            service.analyze_vesting("w", "s", "Synthetic", request)
    else:
        result = service.analyze_vesting("w", "s", "Synthetic", request)
        assert len(result.employee_details) == 2
        assert all(row.annual_hours_worked is None for row in result.employee_details)
        assert all(row.current_vesting_pct == 1 for row in result.employee_details)
