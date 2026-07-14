"""Isolated integration coverage for post-termination event integrity."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.validation import EventSequenceRule
from tests.fixtures.post_termination_events import (
    SAFE_ROOT_CAUSE_FIELDS,
    aggregate_root_causes,
    ordered_run_aggregates,
    synthetic_root_cause_records,
    synthetic_sequence_events,
)

pytestmark = [pytest.mark.integration, pytest.mark.dbt]


@pytest.fixture
def isolated_event_database(tmp_path: Path) -> Path:
    """Create a disposable DuckDB containing only synthetic event rows."""
    database_path = tmp_path / "post-termination.duckdb"
    rows = synthetic_sequence_events()
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE fct_yearly_events (
              scenario_id VARCHAR,
              plan_design_id VARCHAR,
              employee_id VARCHAR,
              event_type VARCHAR,
              simulation_year INTEGER,
              effective_date DATE
            )
            """
        )
        connection.executemany(
            "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    row["scenario_id"],
                    row["plan_design_id"],
                    row["employee_id"],
                    row["event_type"],
                    row["simulation_year"],
                    row["effective_date"],
                )
                for row in rows
            ],
        )
    return database_path


def test_harness_uses_disposable_synthetic_database(
    isolated_event_database: Path,
) -> None:
    assert isolated_event_database.name == "post-termination.duckdb"
    with duckdb.connect(str(isolated_event_database), read_only=True) as connection:
        count = connection.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
    assert count == (len(synthetic_sequence_events()),)


def test_safe_root_cause_aggregates_are_ordered_and_reconcile() -> None:
    aggregates = aggregate_root_causes(synthetic_root_cause_records())
    assert aggregates == sorted(
        aggregates,
        key=lambda row: tuple(row[field] for field in SAFE_ROOT_CAUSE_FIELDS[:-1]),
    )
    assert sum(row["affected_event_count"] for row in aggregates) == 3
    assert (
        sum(
            row["affected_event_count"]
            for row in aggregates
            if row["simulation_year"] == 2026
        )
        == 3
    )
    assert {row["generation_path"] for row in aggregates} == {
        "eligibility_generator",
        "enrollment_opt_out",
    }


def test_safe_root_cause_aggregates_exclude_prohibited_fields() -> None:
    aggregates = aggregate_root_causes(synthetic_root_cause_records())
    prohibited = {
        "employee_id",
        "employee_ssn",
        "effective_date",
        "termination_date",
        "compensation_amount",
        "event_details",
        "database_path",
    }
    assert aggregates
    assert all(tuple(row) == SAFE_ROOT_CAUSE_FIELDS for row in aggregates)
    assert all(prohibited.isdisjoint(row) for row in aggregates)


@pytest.mark.parametrize(
    "relative_path",
    [
        "dbt/models/intermediate/events/int_eligibility_events.sql",
        "dbt/models/intermediate/int_enrollment_events.sql",
        "dbt/models/intermediate/events/int_promotion_events.sql",
        "dbt/models/intermediate/events/int_merit_events.sql",
        "dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql",
    ],
)
def test_event_producers_consume_shared_termination_boundary(
    relative_path: str,
) -> None:
    source = Path(relative_path).read_text(encoding="utf-8")
    assert "ref('int_employee_termination_dates')" in source
    assert "termination_date" in source


def test_enrollment_filters_candidates_before_priority_deduplication() -> None:
    source = Path("dbt/models/intermediate/int_enrollment_events.sql").read_text(
        encoding="utf-8"
    )
    filter_position = source.index("sequence_eligible_events AS")
    priority_position = source.index("deduplicated_events AS")
    assert filter_position < priority_position
    assert "FROM sequence_eligible_events" in source[priority_position:]
    assert (
        "effective_date <= t.termination_date"
        in source[filter_position:priority_position]
    )


def test_synthetic_boundary_retains_same_day_and_valid_enrollment_fallback() -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            """
            CREATE TABLE terminations (
              employee_id VARCHAR, simulation_year INTEGER,
              termination_date DATE, cohort VARCHAR
            );
            INSERT INTO terminations VALUES
              ('experienced', 2026, DATE '2026-06-15', 'experienced'),
              ('new-hire', 2026, DATE '2026-04-01', 'new_hire');
            CREATE TABLE candidates (
              employee_id VARCHAR, event_type VARCHAR, simulation_year INTEGER,
              effective_date DATE, event_category VARCHAR, priority INTEGER
            );
            INSERT INTO candidates VALUES
              ('experienced', 'eligibility', 2026, DATE '2026-06-01', 'eligibility', 1),
              ('experienced', 'promotion', 2026, DATE '2026-06-15', 'promotion', 1),
              ('experienced', 'raise', 2026, DATE '2026-07-01', 'merit', 1),
              ('experienced', 'deferral_escalation', 2026, DATE '2026-07-01', 'deferral', 1),
              ('new-hire', 'eligibility', 2026, DATE '2026-05-01', 'eligibility', 1),
              ('new-hire', 'enrollment', 2026, DATE '2026-03-15', 'auto_enrollment', 4),
              ('new-hire', 'enrollment', 2026, DATE '2026-05-01', 'voluntary_enrollment', 1),
              ('new-hire', 'enrollment_change', 2026, DATE '2026-05-15', 'enrollment_opt_out', 1)
            """
        )
        retained = connection.execute(
            """
            WITH sequence_eligible AS (
              SELECT c.*
              FROM candidates c
              LEFT JOIN terminations t USING (employee_id, simulation_year)
              WHERE t.termination_date IS NULL
                 OR c.effective_date <= t.termination_date
            ),
            prioritized AS (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY employee_id, simulation_year, event_type
                ORDER BY priority, effective_date
              ) AS event_rank
              FROM sequence_eligible
            )
            SELECT employee_id, event_type, effective_date, event_category
            FROM prioritized
            WHERE event_rank = 1
            ORDER BY employee_id, event_type
            """
        ).fetchall()
        assert retained == [
            ("experienced", "eligibility", date(2026, 6, 1), "eligibility"),
            ("experienced", "promotion", date(2026, 6, 15), "promotion"),
            ("new-hire", "enrollment", date(2026, 3, 15), "auto_enrollment"),
        ]
        connection.execute(
            """
            CREATE TABLE fct_yearly_events AS
            SELECT 'scenario-a'::VARCHAR AS scenario_id,
                   'plan-a'::VARCHAR AS plan_design_id,
                   employee_id, 'termination'::VARCHAR AS event_type,
                   simulation_year, termination_date AS effective_date
            FROM terminations
            UNION ALL
            SELECT 'scenario-a', 'plan-a', employee_id, event_type,
                   2026, effective_date
            FROM (
              VALUES
                ('experienced', 'eligibility', DATE '2026-06-01'),
                ('experienced', 'promotion', DATE '2026-06-15'),
                ('new-hire', 'enrollment', DATE '2026-03-15')
            ) AS retained(employee_id, event_type, effective_date)
            """
        )
        result = EventSequenceRule().validate(connection, 2026)
    finally:
        connection.close()
    assert result.passed is True
    assert result.affected_records == 0


def test_ordered_aggregates_are_deterministic_and_ignore_audit_fields() -> None:
    events = [
        {
            "simulation_year": 2026,
            "event_type": "HIRE",
            "event_id": "uuid-a",
            "created_at": "first",
        },
        {
            "simulation_year": 2026,
            "event_type": "termination",
            "event_id": "uuid-b",
            "created_at": "first",
        },
    ]
    reconciliations = [
        {
            "simulation_year": 2026,
            "opening_workforce": 10,
            "hires": 1,
            "terminations": 1,
            "actual_closing_workforce": 10,
            "variance": 0,
        }
    ]
    validations = [
        {
            "simulation_year": 2026,
            "check_name": "event_sequence_validation",
            "passed": True,
            "affected_record_count": 0,
        }
    ]
    first = ordered_run_aggregates(events, reconciliations, validations)
    repeated = [dict(row, event_id="different", created_at="later") for row in events]
    second = ordered_run_aggregates(repeated[::-1], reconciliations, validations)
    assert first == second
    assert first["reconciliations"][0][-1] == 0
    assert first["validations"][0][-1] == 0


def test_prior_year_termination_cannot_resurrect_in_later_aggregate() -> None:
    events = [
        {"simulation_year": 2025, "event_type": "termination"},
        {"simulation_year": 2026, "event_type": "hire"},
    ]
    aggregates = ordered_run_aggregates(events, [], [])
    assert aggregates["event_counts"] == (
        (2025, "termination", 1),
        (2026, "hire", 1),
    )
    assert (2026, "raise", 1) not in aggregates["event_counts"]


def test_corrected_delta_is_limited_to_invalid_activity() -> None:
    baseline = [
        {"simulation_year": 2026, "event_type": "hire"},
        {"simulation_year": 2026, "event_type": "eligibility"},
        {"simulation_year": 2026, "event_type": "enrollment"},
    ]
    corrected = [{"simulation_year": 2026, "event_type": "hire"}]
    baseline_counts = ordered_run_aggregates(baseline, [], [])["event_counts"]
    corrected_counts = ordered_run_aggregates(corrected, [], [])["event_counts"]
    assert set(baseline_counts) - set(corrected_counts) == {
        (2026, "eligibility", 1),
        (2026, "enrollment", 1),
    }
