"""Layer-1 grandfathered employer-cost splice tests (#629)."""

from pathlib import Path
from unittest.mock import MagicMock

import duckdb

from planalign_api.models.employer_cost import ForfeiturePolicy
from planalign_api.models.vesting import VestingScheduleConfig, VestingScheduleType
from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.employer_cost_service import build_employer_cost_offsets
from planalign_api.services.vesting_service import project_forfeitures_for_connection


def _database(path: Path, rows: list[tuple], seed: int | None = None) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER,
            employee_hire_date DATE,
            employer_match_amount DECIMAL(12, 2),
            employer_core_amount DECIMAL(12, 2),
            prorated_annual_compensation DECIMAL(12, 2)
        )
        """
    )
    conn.executemany(
        "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?)", rows
    )
    if seed is not None:
        conn.execute(
            """
            CREATE TABLE run_metadata (
                random_seed INTEGER,
                run_timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO run_metadata VALUES (?, TIMESTAMP '2026-08-28 12:00:00')",
            [seed],
        )
    conn.close()


def _service(paths: dict[str, Path]) -> AnalyticsService:
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda _workspace, scenario: ResolvedDatabasePath(
        path=paths[scenario], source="scenario"
    )
    return AnalyticsService(storage=MagicMock(), db_resolver=resolver)


def _cliff_4() -> VestingScheduleConfig:
    return VestingScheduleConfig(
        schedule_type=VestingScheduleType.CLIFF_4_YEAR,
        name="4-Year Cliff",
    )


def _forfeiture_database(path: Path) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(
        """
        CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR,
            simulation_year INTEGER,
            employee_hire_date DATE,
            employment_status VARCHAR,
            current_tenure INTEGER,
            tenure_band VARCHAR,
            annual_hours_worked INTEGER,
            total_employer_contributions DECIMAL(12, 2),
            employer_match_amount DECIMAL(12, 2),
            employer_core_amount DECIMAL(12, 2),
            prorated_annual_compensation DECIMAL(12, 2)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fct_workforce_snapshot VALUES
            ('old', 2025, DATE '2020-01-01', 'ACTIVE', 5, '5-9', 2080, 1000, 700, 300, 100000),
            ('old', 2026, DATE '2020-01-01', 'ACTIVE', 6, '5-9', 2080, 1000, 700, 300, 100000),
            ('old', 2027, DATE '2020-01-01', 'TERMINATED', 3, '2-4', 1040, 0, 0, 0, 50000),
            ('new', 2025, DATE '2026-01-01', 'ACTIVE', 0, '<2', 2080, 0, 0, 0, 0),
            ('new', 2026, DATE '2026-01-01', 'ACTIVE', 0, '<2', 2080, 900, 600, 300, 80000),
            ('new', 2027, DATE '2026-01-01', 'ACTIVE', 1, '<2', 2080, 900, 600, 300, 80000),
            ('new', 2028, DATE '2026-01-01', 'TERMINATED', 1, '<2', 1040, 0, 0, 0, 40000),
            ('stayer', 2025, DATE '2010-01-01', 'ACTIVE', 15, '10-19', 2080, 100, 70, 30, 10000),
            ('stayer', 2026, DATE '2010-01-01', 'ACTIVE', 16, '10-19', 2080, 100, 70, 30, 10000),
            ('stayer', 2027, DATE '2010-01-01', 'ACTIVE', 17, '10-19', 2080, 100, 70, 30, 10000),
            ('stayer', 2028, DATE '2010-01-01', 'ACTIVE', 18, '10-19', 2080, 100, 70, 30, 10000),
            ('stayer', 2029, DATE '2010-01-01', 'ACTIVE', 19, '10-19', 2080, 100, 70, 30, 10000)
        """
    )
    conn.close()


def _matching_rows(old_cost: int, new_cost: int) -> list[tuple]:
    return [
        ("existing", 2025, "2020-01-01", old_cost, 0, 100_000),
        ("existing", 2026, "2020-01-01", old_cost, 0, 105_000),
        ("new", 2026, "2026-01-01", new_cost, 0, 80_000),
    ]


def test_matching_populations_splice_complementary_cohorts(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400))
    _database(proposal, _matching_rows(2_000, 900))

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2026
    )

    assert [
        (row.year, row.total_employer_cost) for row in result.scenarios[0].years
    ] == [
        (2025, 1_000.0),
        (2026, 1_900.0),
    ]
    assert all(row.available for row in result.scenarios[0].years)


def test_spliced_offsets_tie_exactly_to_unfiltered_projection(tmp_path: Path) -> None:
    path = tmp_path / "scenario.duckdb"
    _forfeiture_database(path)

    result = _service({"base": path}).get_grandfathered_cost_comparison(
        "workspace",
        "base",
        {"base": "Baseline"},
        2026,
        _cliff_4(),
        ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
    )

    conn = duckdb.connect(str(path), read_only=True)
    try:
        expected = build_employer_cost_offsets(
            project_forfeitures_for_connection(conn, _cliff_4()),
            ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
        )
    finally:
        conn.close()

    assert result.scenarios[0].employer_cost_offsets == expected


def test_spliced_reallocation_discloses_each_cohorts_forfeitures(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scenario.duckdb"
    _forfeiture_database(path)

    result = _service({"base": path}).get_grandfathered_cost_comparison(
        "workspace",
        "base",
        {"base": "Baseline"},
        2026,
        _cliff_4(),
        ForfeiturePolicy.REALLOCATE_TO_PARTICIPANTS,
    )

    offsets = {
        row.simulation_year: row for row in result.scenarios[0].employer_cost_offsets
    }
    assert offsets[2028].offset_amount == 0
    assert offsets[2028].participant_allocation == 2000
    assert offsets[2029].offset_amount == 0
    assert offsets[2029].participant_allocation == 1800


def test_baseline_series_is_supported_when_it_is_in_the_comparison(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.duckdb"
    _database(baseline, _matching_rows(1_000, 400))

    result = _service({"base": baseline}).get_grandfathered_cost_comparison(
        "workspace", "base", {"base": "Baseline"}, 2026
    )

    assert [row.total_employer_cost for row in result.scenarios[0].years] == [
        1_000.0,
        1_400.0,
    ]


def test_seed_mismatch_is_reported_as_a_warning(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400), seed=42)
    _database(proposal, _matching_rows(2_000, 900), seed=99)

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2026
    )

    assert result.warnings == ["New design uses random seed 99; the baseline uses 42."]


def test_matching_seeds_do_not_emit_a_warning(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400), seed=42)
    _database(proposal, _matching_rows(2_000, 900), seed=42)

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2026
    )

    assert result.warnings == []


def test_mismatched_population_refuses_only_affected_year(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400))
    rows = _matching_rows(2_000, 900)
    rows[1] = (*rows[1][:-1], 104_999)
    _database(proposal, rows)

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2026
    )

    first, second = result.scenarios[0].years
    assert first.available is True
    assert second.available is False
    assert second.total_employer_cost is None
    assert "total compensation" in second.unavailable_reason


def test_cutoff_before_horizon_uses_proposed_run_only(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400))
    _database(proposal, _matching_rows(2_000, 900))

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2020
    )

    assert [row.total_employer_cost for row in result.scenarios[0].years] == [
        2_000.0,
        2_900.0,
    ]


def test_cutoff_after_horizon_uses_baseline_run_only(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400))
    _database(proposal, _matching_rows(2_000, 900))

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2030
    )

    assert [row.total_employer_cost for row in result.scenarios[0].years] == [
        1_000.0,
        1_400.0,
    ]


def test_cutoff_equal_first_year_keeps_starting_census_on_baseline(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.duckdb"
    proposal = tmp_path / "proposal.duckdb"
    _database(baseline, _matching_rows(1_000, 400))
    _database(proposal, _matching_rows(2_000, 900))

    result = _service(
        {"base": baseline, "new": proposal}
    ).get_grandfathered_cost_comparison(
        "workspace", "base", {"new": "New design"}, 2025
    )

    assert [row.total_employer_cost for row in result.scenarios[0].years] == [
        1_000.0,
        1_900.0,
    ]
