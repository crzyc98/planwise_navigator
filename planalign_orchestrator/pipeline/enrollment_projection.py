"""Build the prior-enrollment input used by each event-generation year.

The projection is deliberately disposable.  It translates the immutable event
ledger into the compact decision state needed by enrollment models without
making a dbt model depend on its own materialized history.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrollmentProjectionResult:
    """Audit metadata for one atomic projection rebuild."""

    decision_year: int
    scenario_id: str
    plan_design_id: str
    employee_count: int


class EnrollmentDecisionProjection:
    """Rebuild scenario-scoped enrollment decision state from authoritative data."""

    table_name = "enrollment_decision_projection"

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        self.db_manager = db_manager

    def ensure_table(self) -> None:
        """Create the empty dbt source relation before any model can resolve it."""

        def _create(conn) -> None:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                  employee_id VARCHAR,
                  decision_year INTEGER NOT NULL,
                  scenario_id VARCHAR NOT NULL,
                  plan_design_id VARCHAR NOT NULL,
                  enrollment_date DATE,
                  is_enrolled BOOLEAN NOT NULL,
                  ever_opted_out BOOLEAN NOT NULL,
                  enrollment_source VARCHAR NOT NULL,
                  current_deferral_rate DECIMAL(9, 6),
                  latest_event_id VARCHAR,
                  latest_event_year INTEGER,
                  latest_event_effective_date DATE
                )
                """
            )

        self.db_manager.execute_with_retry(_create, deterministic=True)

    def rebuild(
        self,
        decision_year: int,
        scenario_id: str = "default",
        plan_design_id: str = "default",
    ) -> EnrollmentProjectionResult:
        """Atomically replace the projection for a single decision year and scope."""

        def _rebuild(conn):
            temp_table = f"{self.table_name}_next"
            conn.execute(f"DROP TABLE IF EXISTS {temp_table}")
            has_event_ledger = conn.execute(
                """SELECT COUNT(*) > 0 FROM information_schema.tables
                   WHERE table_schema = 'main' AND table_name = 'fct_yearly_events'"""
            ).fetchone()[0]
            prior_events = (
                """
                  SELECT
                    employee_id, event_type, effective_date, simulation_year,
                    event_sequence, event_id, event_details, employee_deferral_rate,
                    ROW_NUMBER() OVER (
                      PARTITION BY employee_id
                      ORDER BY effective_date DESC, simulation_year DESC,
                        event_sequence DESC, event_id DESC
                    ) AS latest_rank
                  FROM fct_yearly_events
                  WHERE scenario_id = ?
                    AND plan_design_id = ?
                    AND simulation_year < ?
                    AND event_type IN ('enrollment', 'enrollment_change')
                    AND employee_id IS NOT NULL
            """
                if has_event_ledger
                else """
                  SELECT
                    CAST(NULL AS VARCHAR) AS employee_id,
                    CAST(NULL AS VARCHAR) AS event_type,
                    CAST(NULL AS DATE) AS effective_date,
                    CAST(NULL AS INTEGER) AS simulation_year,
                    CAST(NULL AS INTEGER) AS event_sequence,
                    CAST(NULL AS VARCHAR) AS event_id,
                    CAST(NULL AS VARCHAR) AS event_details,
                    CAST(NULL AS DECIMAL(9, 6)) AS employee_deferral_rate,
                    CAST(NULL AS BIGINT) AS latest_rank
                  WHERE false
            """
            )
            parameters = [decision_year, scenario_id, plan_design_id]
            if has_event_ledger:
                parameters = [scenario_id, plan_design_id, decision_year, *parameters]
            conn.execute(
                f"""
                CREATE TABLE {temp_table} AS
                WITH baseline AS (
                  SELECT
                    employee_id,
                    employee_enrollment_date AS enrollment_date,
                    employee_deferral_rate AS current_deferral_rate,
                    COALESCE(is_enrolled_at_census, false) AS baseline_is_enrolled
                  FROM int_baseline_workforce
                  WHERE employee_id IS NOT NULL
                ),
                prior_events AS (
                  {prior_events}
                ),
                event_state AS (
                  SELECT
                    employee_id,
                    MIN(CASE WHEN event_type = 'enrollment' THEN effective_date END) AS first_enrollment_date,
                    MAX(CASE WHEN event_type = 'enrollment_change'
                              AND LOWER(COALESCE(event_details, '')) LIKE '%opt-out%'
                             THEN 1 ELSE 0 END) = 1 AS ever_opted_out,
                    MAX(CASE WHEN latest_rank = 1
                              AND event_type = 'enrollment_change'
                              AND LOWER(COALESCE(event_details, '')) LIKE '%opt-out%'
                             THEN 1 ELSE 0 END) = 1 AS latest_is_opt_out,
                    MAX(CASE WHEN latest_rank = 1 THEN 1 ELSE 0 END) = 1 AS has_event,
                    MAX(CASE WHEN latest_rank = 1 THEN employee_deferral_rate END) AS current_deferral_rate,
                    MAX(CASE WHEN latest_rank = 1 THEN event_id END) AS latest_event_id,
                    MAX(CASE WHEN latest_rank = 1 THEN simulation_year END) AS latest_event_year,
                    MAX(CASE WHEN latest_rank = 1 THEN effective_date END) AS latest_event_effective_date
                  FROM prior_events
                  GROUP BY employee_id
                )
                SELECT
                  COALESCE(b.employee_id, e.employee_id) AS employee_id,
                  ?::INTEGER AS decision_year,
                  ?::VARCHAR AS scenario_id,
                  ?::VARCHAR AS plan_design_id,
                  COALESCE(e.first_enrollment_date, b.enrollment_date) AS enrollment_date,
                  CASE
                    WHEN COALESCE(e.latest_is_opt_out, false) THEN false
                    WHEN COALESCE(e.has_event, false) THEN true
                    ELSE COALESCE(b.baseline_is_enrolled, false)
                  END AS is_enrolled,
                  COALESCE(e.ever_opted_out, false) AS ever_opted_out,
                  CASE WHEN COALESCE(e.has_event, false) THEN 'fct_yearly_events'
                       ELSE 'baseline_census' END AS enrollment_source,
                  COALESCE(e.current_deferral_rate, b.current_deferral_rate) AS current_deferral_rate,
                  e.latest_event_id,
                  e.latest_event_year,
                  e.latest_event_effective_date
                FROM baseline b
                FULL OUTER JOIN event_state e ON b.employee_id = e.employee_id
                """,
                parameters,
            )
            duplicates = conn.execute(
                f"SELECT COUNT(*) - COUNT(DISTINCT employee_id) FROM {temp_table}"
            ).fetchone()[0]
            if duplicates:
                raise RuntimeError(
                    "Enrollment projection contains duplicate employee state"
                )
            conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")
            conn.execute(f"ALTER TABLE {temp_table} RENAME TO {self.table_name}")
            return conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0]

        count = self.db_manager.execute_with_retry(_rebuild, deterministic=True)
        logger.info(
            "Rebuilt enrollment decision projection for year %d (%s/%s): %d employees",
            decision_year,
            scenario_id,
            plan_design_id,
            count,
        )
        return EnrollmentProjectionResult(
            decision_year, scenario_id, plan_design_id, count
        )
