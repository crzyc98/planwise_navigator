"""Honesty behavior for undefined and unsupported evidence."""

import pytest

from planalign_evidence.service import (
    EvidenceTarget,
    UnsupportedEvidenceError,
    build_evidence_pack,
)
from tests.fixtures.evidence_pack import DEFAULT_ROWS, create_evidence_scenario


@pytest.mark.fast
def test_zero_retained_compensation_is_undefined_and_stays_in_residual(
    tmp_path,
) -> None:
    rows = tuple(
        tuple(0 if index == 3 else value for index, value in enumerate(row))
        for row in DEFAULT_ROWS
    )
    scenario = create_evidence_scenario(tmp_path, rows=rows)
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    pack = build_evidence_pack(target, "employer_match_cost", 2025, 2027)
    assert pack.drivers[2].contribution.status == "undefined"
    assert pack.drivers[3].contribution.status == "undefined"
    assert pack.residual.contribution.value == "4"
    assert pack.residual.material


@pytest.mark.fast
def test_missing_metric_column_is_not_reported_as_zero(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    import duckdb

    with duckdb.connect(str(scenario.database_path)) as connection:
        connection.execute(
            "ALTER TABLE fct_workforce_snapshot DROP COLUMN employer_match_amount"
        )
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    with pytest.raises(UnsupportedEvidenceError, match="missing columns") as error:
        build_evidence_pack(target, "employer_match_cost", 2025, 2027)
    assert error.value.missing_columns == ("employer_match_amount",)


@pytest.mark.fast
def test_zero_change_suppresses_shares_but_keeps_residual(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    pack = build_evidence_pack(target, "active_headcount", 2025, 2027)
    assert pack.change.total_change.value == "0"
    assert all(driver.share_of_change.status == "suppressed" for driver in pack.drivers)
    assert pack.residual.contribution.value == "0"
