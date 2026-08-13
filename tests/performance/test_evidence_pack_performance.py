"""Interactive-budget guard for 60,000 employee-years without sampling."""

import time

import pytest

from planalign_ensemble.models import CANONICAL_METRICS
from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from tests.fixtures.evidence_pack import create_evidence_scenario

pytestmark = pytest.mark.performance


def test_all_metrics_complete_within_two_seconds_each_at_60000_employee_years(
    tmp_path,
) -> None:
    rows = []
    for year in (2025, 2027):
        for employee in range(30_000):
            active = employee % 5 != 0 or year == 2027
            compensation = 50_000 + employee % 10_000
            rows.append(
                (
                    f"synthetic-{employee}",
                    year,
                    "active" if active else "terminated",
                    compensation,
                    compensation * 0.03,
                    compensation * 0.05,
                    "participating" if employee % 3 else "not_participating",
                    0.06 if employee % 3 else 0,
                )
            )
    scenario = create_evidence_scenario(tmp_path, rows=tuple(rows))
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    durations = []
    for metric in CANONICAL_METRICS:
        started = time.perf_counter()
        build_evidence_pack(target, metric, 2025, 2027)
        durations.append(time.perf_counter() - started)
    assert max(durations) <= 2.0
