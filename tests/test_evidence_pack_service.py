"""Core cited-decomposition behavior for all canonical metrics."""

from decimal import Decimal

import pytest

from planalign_ensemble.models import CANONICAL_METRICS, METRIC_REGISTRY
from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from tests.fixtures.evidence_pack import create_evidence_scenario


@pytest.fixture
def target(tmp_path):
    scenario = create_evidence_scenario(tmp_path)
    return EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
        scenario.workspace_id,
        "Evidence Scenario",
    )


@pytest.mark.fast
@pytest.mark.parametrize("metric", CANONICAL_METRICS)
def test_all_metrics_reconcile_in_fixed_driver_order(target, metric) -> None:
    pack = build_evidence_pack(target, metric, 2025, 2027)

    assert (
        tuple(driver.id for driver in pack.drivers)
        == METRIC_REGISTRY[metric].driver_ids
    )
    explained = sum(
        (Decimal(driver.contribution.value or "0") for driver in pack.drivers),
        Decimal(pack.residual.contribution.value or "0"),
    )
    assert explained == Decimal(pack.change.total_change.value or "0")
    assert pack.residual.contribution.value == "0"
    assert pack == build_evidence_pack(target, metric, 2025, 2027)


@pytest.mark.fast
def test_known_cohorts_and_symmetric_cost_factorization(target) -> None:
    headcount = build_evidence_pack(target, "active_headcount", 2025, 2027)
    assert [driver.contribution.value for driver in headcount.drivers] == [
        "1",
        "-1",
        "1",
        "-1",
    ]

    match = build_evidence_pack(target, "employer_match_cost", 2025, 2027)
    assert [driver.contribution.value for driver in match.drivers] == [
        "8",
        "-6",
        "-1.625",
        "5.625",
    ]
    assert [driver.population.count.value for driver in match.drivers] == [
        "1",
        "1",
        "3",
        "3",
    ]


@pytest.mark.fast
def test_canonical_ratio_population_includes_inactive_rows(target) -> None:
    participation = build_evidence_pack(target, "participation_rate", 2025, 2027)
    deferral = build_evidence_pack(target, "avg_deferral_rate", 2025, 2027)
    assert participation.change.base_value.value == "0.5"
    assert participation.change.target_value.value == "0.75"
    assert deferral.change.base_value.value == "0.0275"
    assert deferral.change.target_value.value == "0.045"
