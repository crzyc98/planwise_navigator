"""Aggregate-only comparison behavior for independent scenario stores."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from planalign_ensemble.models import CANONICAL_METRICS
from planalign_evidence.cross_models import CROSS_DRIVER_IDS
from planalign_evidence.cross_service import build_cross_scenario_evidence_pack
from planalign_evidence.service import EvidenceTarget, UnsupportedEvidenceError
from tests.fixtures.evidence_pack import DEFAULT_ROWS, create_evidence_scenario


def _target(scenario) -> EvidenceTarget:
    return EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
        scenario.workspace_id,
        "Evidence Scenario",
    )


@pytest.fixture
def targets(tmp_path):
    a = create_evidence_scenario(tmp_path, scenario_id="scenario-a")
    rows_b = tuple(
        (row[0], row[1], row[2], row[3] + 25, row[4] + 2, row[5] + 3, row[6], row[7])
        for row in DEFAULT_ROWS
    )
    b = create_evidence_scenario(tmp_path, rows=rows_b, scenario_id="scenario-b")
    return _target(a), _target(b)


@pytest.mark.fast
@pytest.mark.parametrize("metric", CANONICAL_METRICS)
def test_all_metrics_reconcile_and_bind_each_store(targets, metric) -> None:
    a, b = targets
    pack = build_cross_scenario_evidence_pack(a, b, metric, 2025)
    explained = sum(
        (
            Decimal(d.contribution.value or "0")
            for d in pack.drivers
            if d.contribution.status == "defined"
        ),
        Decimal(pack.residual.contribution.value or "0"),
    )
    assert explained == Decimal(pack.change.total_change.value or "0")
    assert tuple(d.id for d in pack.drivers) == CROSS_DRIVER_IDS[metric]
    assert pack == build_cross_scenario_evidence_pack(a, b, metric, 2025)
    for figure in pack._figures():
        for citation in figure.citations:
            assert citation.result_store == (
                a.result_store if citation.query_id == "QA" else b.result_store
            )


@pytest.mark.fast
def test_zero_compensation_base_reports_unexplained_movement(tmp_path) -> None:
    a = create_evidence_scenario(tmp_path, scenario_id="scenario-a")
    rows_b = tuple(
        (
            row[0],
            row[1],
            row[2],
            0 if row[1] == 2025 else row[3],
            row[4] + 2 if row[1] == 2025 else row[4],
            row[5],
            row[6],
            row[7],
        )
        for row in DEFAULT_ROWS
    )
    b = create_evidence_scenario(tmp_path, rows=rows_b, scenario_id="scenario-b")
    pack = build_cross_scenario_evidence_pack(
        _target(a), _target(b), "employer_match_cost", 2025
    )
    assert all(d.contribution.status == "undefined" for d in pack.drivers)
    assert pack.residual.contribution.value == pack.change.total_change.value
    assert "residual_dominates" in {warning.code for warning in pack.warnings}


@pytest.mark.fast
def test_missing_year_on_one_side(tmp_path) -> None:
    a = create_evidence_scenario(tmp_path, scenario_id="scenario-a")
    b = create_evidence_scenario(
        tmp_path, rows=DEFAULT_ROWS[4:], scenario_id="scenario-b"
    )
    with pytest.raises(UnsupportedEvidenceError, match="scenario_b"):
        build_cross_scenario_evidence_pack(
            _target(a), _target(b), "active_headcount", 2025
        )


@pytest.mark.fast
def test_same_scenario_rejected(targets) -> None:
    with pytest.raises(UnsupportedEvidenceError, match="distinct scenarios"):
        build_cross_scenario_evidence_pack(
            targets[0], targets[0], "active_headcount", 2025
        )


@pytest.mark.fast
def test_pack_rejects_driver_order_and_reconciliation(targets) -> None:
    pack = build_cross_scenario_evidence_pack(*targets, "total_compensation", 2025)
    with pytest.raises(ValidationError, match="driver order"):
        type(pack).model_validate(
            {**pack.model_dump(), "drivers": tuple(reversed(pack.drivers))}
        )
    bad = pack.model_dump()
    bad["residual"]["contribution"]["value"] = "1000"
    with pytest.raises(ValidationError, match="reconcile"):
        type(pack).model_validate(bad)


def _seed_warnings(pack) -> list[tuple[str, str]]:
    return [
        (w.severity, w.message)
        for w in pack.warnings
        if w.code == "scenario_seed_mismatch"
    ]


@pytest.mark.fast
def test_matching_seeds_raise_no_comparability_warning(targets) -> None:
    pack = build_cross_scenario_evidence_pack(*targets, "active_headcount", 2025)
    assert pack.provenance_a.random_seed == pack.provenance_b.random_seed
    assert _seed_warnings(pack) == []


@pytest.mark.fast
@pytest.mark.parametrize(("seed_b", "severity"), [(7, "caution"), (None, "info")])
def test_seed_differences_qualify_the_comparison(targets, seed_b, severity) -> None:
    a, b = targets
    baseline = build_cross_scenario_evidence_pack(a, b, "active_headcount", 2025)
    provenance_b = baseline.provenance_b.model_copy(update={"random_seed": seed_b})
    pack = build_cross_scenario_evidence_pack(
        a, b, "active_headcount", 2025, provenance_b=provenance_b
    )
    [(actual, message)] = _seed_warnings(pack)
    assert actual == severity
    assert "simulation noise" in message


def _add_core_column(scenario, core_by_employee: dict[str, int]) -> None:
    """Split each row's plan cost into match + core, as fct_workforce_snapshot does."""
    import duckdb

    with duckdb.connect(str(scenario.database_path)) as connection:
        connection.execute(
            "ALTER TABLE fct_workforce_snapshot ADD COLUMN employer_core_amount DECIMAL(18, 2)"
        )
        for employee_id, core in core_by_employee.items():
            connection.execute(
                "UPDATE fct_workforce_snapshot SET employer_core_amount = ?, "
                "total_employer_contributions = employer_match_amount + ? "
                "WHERE employee_id = ?",
                [core, core, employee_id],
            )


@pytest.mark.fast
def test_plan_cost_splits_into_cited_match_and_core_components(tmp_path) -> None:
    a = create_evidence_scenario(tmp_path, scenario_id="scenario-a")
    rows_b = tuple((*row[:4], row[4] + 2, *row[5:]) for row in DEFAULT_ROWS)
    b = create_evidence_scenario(tmp_path, rows=rows_b, scenario_id="scenario-b")
    _add_core_column(a, {"a": 3, "b": 4, "c": 0, "d": 3})
    _add_core_column(b, {"a": 0, "b": 0, "c": 0, "d": 0})

    pack = build_cross_scenario_evidence_pack(
        _target(a), _target(b), "total_employer_plan_cost", 2025
    )

    match, core = pack.drivers
    assert (match.id, core.id) == (
        "employer_match_difference",
        "employer_core_difference",
    )
    assert Decimal(match.contribution.value) == Decimal(2 * 4)  # +2 on each 2025 row
    assert Decimal(core.contribution.value) == Decimal(-10)
    assert pack.residual.contribution.value == "0"
    assert [c.result_column for c in match.contribution.citations] == [
        "match_value"
    ] * 2
    assert [c.result_column for c in core.contribution.citations] == ["core_value"] * 2


@pytest.mark.fast
def test_plan_cost_without_core_amounts_is_left_unexplained(targets) -> None:
    pack = build_cross_scenario_evidence_pack(
        *targets, "total_employer_plan_cost", 2025
    )

    assert all(d.contribution.status == "undefined" for d in pack.drivers)
    assert pack.residual.contribution.value == pack.change.total_change.value


@pytest.mark.fast
def test_summary_states_direction_and_rate_cites_its_denominator(targets) -> None:
    pack = build_cross_scenario_evidence_pack(*targets, "employer_match_cost", 2025)

    assert " is higher by $" in pack.executive_summary[0]
    rate = next(d for d in pack.drivers if d.rate_a is not None).rate_a
    assert [c.result_column for c in rate.citations] == ["value", "compensation_base"]
