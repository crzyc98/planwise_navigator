"""Full-scale, env-driven parity contracts for Feature 122 migration gates."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pytest

from planalign_core.constants import (
    MODEL_FCT_WORKFORCE_SNAPSHOT,
    MODEL_FCT_YEARLY_EVENTS,
)
from planalign_orchestrator.change_validation import run_frozen_validation
from planalign_orchestrator.pipeline.workflow import WorkflowStage

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.integration

CONSUMER_PARITY_COLUMNS = {
    "eligibility": (
        "int_employer_eligibility",
        "employee_id, simulation_year, employment_status, current_tenure, "
        "scheduled_hours_per_week, annual_hours_worked, eligible_for_match, "
        "match_eligibility_reason, eligible_for_core, eligible_for_contributions",
    ),
    "employee_contribution": (
        "int_employee_contributions",
        "employee_id, simulation_year, annual_contribution_amount, "
        "effective_annual_deferral_rate, total_contribution_base_compensation, "
        "number_of_contribution_periods, total_contribution_days, "
        "prorated_annual_compensation, employment_status, is_enrolled_flag, "
        "final_deferral_rate",
    ),
    "employer_core": (
        "int_employer_core_contributions",
        "employee_id, simulation_year, eligible_compensation, employment_status, "
        "eligible_for_core, annual_hours_worked, employer_core_amount, "
        "core_contribution_rate, contribution_method",
    ),
    "employee_match": (
        "int_employee_match_calculations",
        "employee_id, simulation_year, eligible_compensation, deferral_rate, "
        "annual_deferrals, employer_match_amount, is_eligible_for_match, "
        "match_eligibility_reason, effective_match_rate",
    ),
    "proration": (
        MODEL_FCT_WORKFORCE_SNAPSHOT,
        "employee_id, simulation_year, current_compensation, "
        "prorated_annual_compensation, full_year_equivalent_compensation, "
        "annual_hours_worked, scheduled_hours_per_week",
    ),
}


def _required_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"{variable} is not configured")
    path = Path(value)
    assert path.is_file(), f"{variable} does not identify a file: {path}"
    return path


def _successful_publication_counts(sample: dict) -> dict[int, Counter[str]]:
    counts: dict[int, Counter[str]] = defaultdict(Counter)
    for invocation in sample["invocations"]:
        year = invocation.get("year")
        if year is None:
            continue
        for model in invocation.get("models", []):
            if model.get("status") == "success":
                counts[year][model["unique_id"].rsplit(".", 1)[-1]] += 1
    return counts


def _bidirectional_difference_count(
    baseline: Path,
    candidate: Path,
    relation: str,
    projection: str,
) -> tuple[int, int]:
    baseline_path = str(baseline).replace("'", "''")
    candidate_path = str(candidate).replace("'", "''")
    with duckdb.connect(database=":memory:") as connection:
        connection.execute(f"ATTACH '{baseline_path}' AS baseline (READ_ONLY)")
        connection.execute(f"ATTACH '{candidate_path}' AS candidate (READ_ONLY)")
        baseline_minus = connection.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM baseline.{relation} "
            f"EXCEPT ALL SELECT {projection} FROM candidate.{relation})"
        ).fetchone()[0]
        candidate_minus = connection.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM candidate.{relation} "
            f"EXCEPT ALL SELECT {projection} FROM baseline.{relation})"
        ).fetchone()[0]
    return baseline_minus, candidate_minus


def test_event_publication_matches_frozen_full_scale_baseline() -> None:
    baseline = _required_path("F122_BASELINE_DB")
    candidate = _required_path("F122_CANDIDATE_DB")

    result = run_frozen_validation(
        repo_root=ROOT,
        baseline_db=baseline,
        candidate_db=candidate,
        characterization_path=ROOT
        / "specs/122-state-pipeline-redesign/baseline-characterization.json",
        exclusions_path=ROOT
        / "specs/122-state-pipeline-redesign/contracts/parity-exclusions.yaml",
        phase="event_publication",
    )

    assert result.passed, result.failures
    events = result.comparisons[MODEL_FCT_YEARLY_EVENTS]
    snapshot = result.comparisons[MODEL_FCT_WORKFORCE_SNAPSHOT]
    assert events.status == snapshot.status == "compared"
    assert events.baseline_schema == events.candidate_schema
    assert events.baseline_group_counts == events.candidate_group_counts
    assert events.baseline_metrics == events.candidate_metrics
    assert snapshot.baseline_schema == snapshot.candidate_schema
    assert snapshot.baseline_group_counts == snapshot.candidate_group_counts
    assert snapshot.baseline_metrics == snapshot.candidate_metrics


def test_event_and_snapshot_publish_once_per_effective_year() -> None:
    sample_path = _required_path("F122_CANDIDATE_SAMPLE")
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    assert sample["completed"] is True
    start_year, end_year = sample["horizon"]

    counts = _successful_publication_counts(sample)

    for year in range(start_year, end_year + 1):
        assert counts[year][MODEL_FCT_YEARLY_EVENTS] == 1
        assert counts[year][MODEL_FCT_WORKFORCE_SNAPSHOT] == 1


def test_consolidated_state_schedule_and_node_execution_counts() -> None:
    sample = json.loads(
        _required_path("F122_CANDIDATE_SAMPLE").read_text(encoding="utf-8")
    )
    start_year, end_year = sample["horizon"]
    whole_run_total = len(sample["invocations"])
    assert whole_run_total > 0  # measured evidence; deliberately no fixed total

    for year in range(start_year, end_year + 1):
        state = [
            item
            for item in sample["invocations"]
            if item.get("year") == year
            and item.get("stage") == WorkflowStage.STATE_ACCUMULATION.value
        ]
        assert len(state) == 1
        assert "--full-refresh" not in state[0]["command"]
        state_nodes = [
            model["unique_id"].rsplit(".", 1)[-1]
            for model in state[0].get("models", [])
            if model.get("status") == "success"
        ]
        assert len(state_nodes) == len(set(state_nodes))
        assert MODEL_FCT_YEARLY_EVENTS not in state_nodes

        publications = [
            item
            for item in sample["invocations"]
            if item.get("year") == year
            and any(
                model["unique_id"].endswith(f".{MODEL_FCT_YEARLY_EVENTS}")
                and model.get("status") == "success"
                for model in item.get("models", [])
            )
        ]
        assert len(publications) == 1
        assert publications[0]["stage"] == WorkflowStage.EVENT_GENERATION.value
        assert publications[0]["seq"] < state[0]["seq"]


@pytest.mark.parametrize(
    ("domain", "relation", "projection"),
    [(domain, *contract) for domain, contract in CONSUMER_PARITY_COLUMNS.items()],
)
def test_consumer_domains_match_frozen_baseline(
    domain: str,
    relation: str,
    projection: str,
) -> None:
    differences = _bidirectional_difference_count(
        _required_path("F122_BASELINE_DB"),
        _required_path("F122_CANDIDATE_DB"),
        relation,
        projection,
    )
    assert differences == (0, 0), f"{domain} parity differences: {differences}"


def test_snapshot_composition_matches_frozen_baseline() -> None:
    baseline = _required_path("F122_BASELINE_DB")
    candidate = _required_path("F122_CANDIDATE_DB")
    with duckdb.connect(str(baseline), read_only=True) as connection:
        columns = [
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? AND column_name != 'snapshot_created_at' "
                "ORDER BY ordinal_position",
                [MODEL_FCT_WORKFORCE_SNAPSHOT],
            ).fetchall()
        ]

    assert columns
    projection = ", ".join(f'"{column}"' for column in columns)
    differences = _bidirectional_difference_count(
        baseline,
        candidate,
        MODEL_FCT_WORKFORCE_SNAPSHOT,
        projection,
    )
    assert differences == (0, 0), f"snapshot composition differences: {differences}"


def test_migrated_consumer_financial_invariants() -> None:
    candidate = _required_path("F122_CANDIDATE_DB")
    with duckdb.connect(str(candidate), read_only=True) as connection:
        violations = connection.execute(
            """SELECT
                (SELECT COUNT(*) FROM int_employee_contributions
                 WHERE annual_contribution_amount < 0
                    OR annual_contribution_amount > applicable_irs_limit),
                (SELECT COUNT(*) FROM int_employer_core_contributions
                 WHERE (NOT eligible_for_core AND employer_core_amount != 0)
                    OR employer_core_amount < 0),
                (SELECT COUNT(*) FROM int_employee_match_calculations
                 WHERE (NOT is_eligible_for_match AND employer_match_amount != 0)
                    OR employer_match_amount < 0),
                (SELECT COUNT(*) FROM int_employer_eligibility
                 WHERE annual_hours_worked < 0)
            """
        ).fetchone()

    assert violations == (0, 0, 0, 0)
