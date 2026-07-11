"""Enterprise-scale gate for fact-backed enrollment projection rebuilds."""

from __future__ import annotations

import json
from pathlib import Path
import time

import duckdb
import psutil
import pytest

from planalign_orchestrator.pipeline.enrollment_projection import (
    EnrollmentDecisionProjection,
)


class DirectConnectionManager:
    def __init__(self, connection):
        self.connection = connection

    def execute_with_retry(self, callback, **_kwargs):
        return callback(self.connection)


BASELINE_PATH = (
    Path(__file__).parent
    / "baselines"
    / "census_enrollment_projection_sql_baseline.json"
)
EMPLOYEES = 100_000
HISTORY_ROWS = 200_000
MAX_SECONDS = 30.0
MAX_RSS_MIB = 1024.0


@pytest.mark.performance
def test_projection_rebuilds_enterprise_scale_within_contract():
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(
            """CREATE TABLE int_baseline_workforce AS
            SELECT 'employee-' || lpad(i::VARCHAR, 6, '0') AS employee_id,
                   DATE '2020-01-01' AS employee_enrollment_date,
                   0.05::DECIMAL(9, 6) AS employee_deferral_rate,
                   i % 2 = 0 AS is_enrolled_at_census
            FROM range(?) AS employees(i)""",
            [EMPLOYEES],
        )
        conn.execute(
            """CREATE TABLE fct_yearly_events AS
            SELECT 'event-' || i::VARCHAR AS event_id, 'default' AS scenario_id,
                   'default' AS plan_design_id,
                   'employee-' || lpad((i % ?)::VARCHAR, 6, '0') AS employee_id,
                   CASE WHEN i % 11 = 0 THEN 'enrollment_change' ELSE 'enrollment' END AS event_type,
                   DATE '2025-06-01' AS effective_date, 2025 AS simulation_year,
                   i AS event_sequence,
                   CASE WHEN i % 11 = 0 THEN 'Auto-enrollment opt-out' ELSE 'Enrollment' END AS event_details,
                   CASE WHEN i % 11 = 0 THEN 0.00 ELSE 0.04 END::DECIMAL(9, 6) AS employee_deferral_rate
            FROM range(?) AS events(i)""",
            [EMPLOYEES, HISTORY_ROWS],
        )
        process = psutil.Process()
        before_rss = process.memory_info().rss
        started = time.monotonic()
        result = EnrollmentDecisionProjection(DirectConnectionManager(conn)).rebuild(
            2026
        )
        elapsed = time.monotonic() - started
        rss_mib = (process.memory_info().rss - before_rss) / (1024 * 1024)

        assert result.employee_count == EMPLOYEES
        assert conn.execute(
            "SELECT COUNT(*) = COUNT(DISTINCT employee_id) FROM enrollment_decision_projection"
        ).fetchone() == (True,)
        assert elapsed <= MAX_SECONDS
        assert rss_mib <= MAX_RSS_MIB

        baseline = json.loads(BASELINE_PATH.read_text())
        assert elapsed <= baseline["runtime_seconds"] * 1.15
        assert rss_mib <= baseline["rss_mib"] * 1.20
    finally:
        conn.close()
