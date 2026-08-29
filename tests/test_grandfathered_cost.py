"""Layer-1 grandfathered employer-cost splice tests (#629)."""

from pathlib import Path
from unittest.mock import MagicMock

import duckdb

from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath


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
