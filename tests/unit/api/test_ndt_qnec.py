"""Uniform QNEC arithmetic and planning guards."""

import pytest

from planalign_api.services.ndt_qnec import NHCEQNECInput, estimate_uniform_qnec

pytestmark = pytest.mark.fast


def test_worked_example() -> None:
    participants = [NHCEQNECInput(100000, 0.04, 4000)] * 10
    result = estimate_uniform_qnec([0.08], participants, 70000)
    assert result.status == "estimate"
    assert result.qnec_rate == pytest.approx(0.02)
    assert result.total_qnec == 20000
    assert result.recipient_count == 10
    assert result.nhce_average_adp_after == pytest.approx(0.06)
    assert result.applied_threshold_after == pytest.approx(0.08)
    assert result.test_result_after == "pass"


@pytest.mark.parametrize(
    "hce,required,test",
    [
        (0.03, 0.015, "alternative"),  # H/2
        (0.04, 0.02, "alternative"),  # alternative branches meet
        (0.08, 0.06, "alternative"),  # H - 0.02
        (0.10, 0.08, "basic"),  # basic and alternative meet
        (0.15, 0.12, "basic"),  # H/1.25
    ],
)
def test_branches_and_zero_deferrers(hce: float, required: float, test: str) -> None:
    result = estimate_uniform_qnec([hce], [NHCEQNECInput(100000, 0, 0)], 70000)
    assert result.qnec_rate == pytest.approx(required)
    assert result.nhce_average_adp_after == pytest.approx(required, abs=1e-7)
    assert result.applied_test_after == test
    assert result.test_result_after == "pass"


def test_unequal_compensation_uses_unweighted_adp() -> None:
    result = estimate_uniform_qnec(
        [0.08],
        [
            NHCEQNECInput(50000, 0.02, 1000),
            NHCEQNECInput(150000, 0.06, 9000),
        ],
        70000,
    )
    assert result.nhce_average_adp_before == pytest.approx(0.04)
    assert result.total_qnec == 4000
    assert result.test_result_after == "pass"


def test_rounds_each_participant_up_to_cent() -> None:
    result = estimate_uniform_qnec([0.031], [NHCEQNECInput(1, 0, 0)] * 2, 70000)
    assert result.total_qnec == 0.04
    assert result.nhce_average_adp_after == 0.02
    assert result.test_result_after == "pass"


def test_passing_needs_no_qnec() -> None:
    result = estimate_uniform_qnec([0.05], [NHCEQNECInput(100000, 0.04, 4000)], 70000)
    assert result.status == "not_needed"
    assert result.total_qnec == 0
    assert result.test_result_after == "pass"


def test_infeasible_does_not_clip_amounts() -> None:
    result = estimate_uniform_qnec([0.08], [NHCEQNECInput(100000, 0.04, 69000)], 70000)
    assert result.status == "infeasible"
    assert result.limit_breach_count == 1
    assert result.total_qnec == 2000
    assert result.test_result_after == "pass"
    assert "1 NHCEs" in result.reason


@pytest.mark.parametrize(
    "hce,nhce", [([], []), ([0.08], []), ([], [NHCEQNECInput(1, 0, 0)])]
)
def test_empty_groups(hce: list[float], nhce: list[NHCEQNECInput]) -> None:
    result = estimate_uniform_qnec(hce, nhce, 70000)
    assert result.status == "unsupported"
    assert result.reason


def test_unavailable_limit() -> None:
    result = estimate_uniform_qnec([0.08], [NHCEQNECInput(100000, 0.04, 999999)], None)
    assert result.status == "estimate"
    assert result.limit_breach_count == 0
    assert "415 headroom not checked: limit unavailable" in result.assumptions
