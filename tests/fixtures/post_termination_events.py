"""Synthetic, non-PII fixtures for post-termination integrity tests."""

from __future__ import annotations

from datetime import date
from typing import Any


EventRow = dict[str, Any]


def event_row(
    employee_id: str,
    event_type: str,
    simulation_year: int,
    effective_date: date | None,
    *,
    scenario_id: str = "scenario-a",
    plan_design_id: str = "plan-a",
) -> EventRow:
    """Build one synthetic authoritative event row."""
    return {
        "scenario_id": scenario_id,
        "plan_design_id": plan_design_id,
        "employee_id": employee_id,
        "event_type": event_type,
        "simulation_year": simulation_year,
        "effective_date": effective_date,
    }


def synthetic_sequence_events() -> list[EventRow]:
    """Cover timing, duplicate, lifetime, missing-date, and scope edge cases."""
    return [
        event_row("experienced", "termination", 2026, date(2026, 6, 15)),
        event_row("experienced", "raise", 2026, date(2026, 6, 1)),
        event_row("experienced", "promotion", 2026, date(2026, 6, 15)),
        event_row("experienced", "enrollment", 2026, date(2026, 7, 1)),
        event_row("new-hire", "hire", 2026, date(2026, 2, 1)),
        event_row("new-hire", "termination", 2026, date(2026, 4, 1)),
        event_row("new-hire", "eligibility", 2026, date(2026, 5, 1)),
        event_row("duplicate-term", "termination", 2026, date(2026, 8, 1)),
        event_row("duplicate-term", "TERMINATION", 2026, date(2026, 3, 1)),
        event_row("duplicate-term", "raise", 2026, date(2026, 4, 1)),
        event_row("prior-year", "termination", 2025, date(2025, 9, 1)),
        event_row("prior-year", "deferral_escalation", 2026, date(2026, 1, 1)),
        event_row("missing-date", "termination", 2026, date(2026, 5, 1)),
        event_row("missing-date", "raise", 2026, None),
        event_row(
            "experienced",
            "raise",
            2026,
            date(2026, 7, 1),
            scenario_id="scenario-b",
        ),
        event_row(
            "experienced",
            "raise",
            2026,
            date(2026, 7, 1),
            plan_design_id="plan-b",
        ),
    ]


SAFE_ROOT_CAUSE_FIELDS = (
    "simulation_year",
    "event_type",
    "termination_cohort",
    "generation_path",
    "state_source",
    "affected_event_count",
)


def aggregate_root_causes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate transient diagnostic rows into the allowed safe projection."""
    dimensions = SAFE_ROOT_CAUSE_FIELDS[:-1]
    counts: dict[tuple[Any, ...], int] = {}
    for record in records:
        key = tuple(record[field] for field in dimensions)
        counts[key] = counts.get(key, 0) + int(record.get("affected_event_count", 1))
    return [
        dict(zip(SAFE_ROOT_CAUSE_FIELDS, (*key, count), strict=True))
        for key, count in sorted(counts.items())
        if count > 0
    ]


def synthetic_root_cause_records() -> list[dict[str, Any]]:
    """Return transient rows with synthetic IDs for safe aggregation tests."""
    return [
        {
            "employee_id": "synthetic-new-hire-1",
            "simulation_year": 2026,
            "event_type": "eligibility",
            "termination_cohort": "same_year_new_hire",
            "generation_path": "eligibility_generator",
            "state_source": "current_year_hire",
        },
        {
            "employee_id": "synthetic-new-hire-2",
            "simulation_year": 2026,
            "event_type": "eligibility",
            "termination_cohort": "same_year_new_hire",
            "generation_path": "eligibility_generator",
            "state_source": "current_year_hire",
        },
        {
            "employee_id": "synthetic-experienced-1",
            "simulation_year": 2026,
            "event_type": "enrollment_change",
            "termination_cohort": "same_year_experienced",
            "generation_path": "enrollment_opt_out",
            "state_source": "current_year_workforce",
        },
    ]


def ordered_run_aggregates(
    event_rows: list[dict[str, Any]],
    reconciliations: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> dict[str, tuple[tuple[Any, ...], ...]]:
    """Project deterministic run comparisons without UUID or audit metadata."""
    event_counts: dict[tuple[int, str], int] = {}
    for row in event_rows:
        key = (int(row["simulation_year"]), str(row["event_type"]).lower())
        event_counts[key] = event_counts.get(key, 0) + 1
    return {
        "event_counts": tuple(
            (*key, count) for key, count in sorted(event_counts.items())
        ),
        "reconciliations": tuple(
            sorted(
                (
                    int(row["simulation_year"]),
                    int(row["opening_workforce"]),
                    int(row["hires"]),
                    int(row["terminations"]),
                    int(row["actual_closing_workforce"]),
                    int(row["variance"]),
                )
                for row in reconciliations
            )
        ),
        "validations": tuple(
            sorted(
                (
                    int(row["simulation_year"]),
                    str(row["check_name"]),
                    bool(row["passed"]),
                    row["affected_record_count"],
                )
                for row in validation_rows
            )
        ),
    }
