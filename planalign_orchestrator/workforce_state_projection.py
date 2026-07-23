"""Build the disposable, strictly-prior workforce input for a decision year."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkforceProjectionResult:
    """PII-safe audit metadata for one projection rebuild."""

    decision_year: int
    scenario_id: str
    plan_design_id: str
    employee_count: int


class WorkforceStateProjection:
    """Atomically expose only year N-1 canonical workforce rows to year N."""

    table_name = "workforce_state_projection"
    _columns: dict[str, str] = {
        "decision_year": "INTEGER NOT NULL",
        "source_simulation_year": "INTEGER",
        "scenario_id": "VARCHAR NOT NULL",
        "plan_design_id": "VARCHAR NOT NULL",
        "employee_id": "VARCHAR",
        "employee_ssn": "VARCHAR",
        "employee_birth_date": "TIMESTAMP",
        "employee_hire_date": "TIMESTAMP",
        "current_compensation": "DOUBLE",
        "full_year_equivalent_compensation": "DOUBLE",
        "current_age": "BIGINT",
        "current_tenure": "INTEGER",
        "level_id": "INTEGER",
        "employment_status": "VARCHAR",
        "termination_date": "TIMESTAMP",
        "scheduled_hours_per_week": "DECIMAL(5, 2)",
    }

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        self.db_manager = db_manager

    def ensure_table(self) -> None:
        """Create the disposable dbt source, replacing any stale schema."""
        definitions = ",\n                  ".join(
            f"{name} {data_type}" for name, data_type in self._columns.items()
        )

        def _ensure(connection) -> None:
            existing = {
                row[0]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'main' AND table_name = ?",
                    [self.table_name],
                ).fetchall()
            }
            if existing and existing != set(self._columns):
                connection.execute(f"DROP TABLE {self.table_name}")
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table_name} ({definitions})"
            )

        self.db_manager.execute_with_retry(_ensure, deterministic=True)

    def rebuild(
        self,
        decision_year: int,
        scenario_id: str = "default",
        plan_design_id: str = "default",
    ) -> WorkforceProjectionResult:
        """Replace the projection with the selected scope's exact N-1 state."""

        def _rebuild(connection) -> int:
            temporary = f"{self.table_name}_next"
            connection.execute(f"DROP TABLE IF EXISTS {temporary}")
            has_accumulator = connection.execute(
                "SELECT COUNT(*) > 0 FROM information_schema.tables "
                "WHERE table_schema = 'main' "
                "AND table_name = 'int_workforce_state_accumulator'"
            ).fetchone()[0]
            if has_accumulator:
                connection.execute(
                    f"""
                    CREATE TABLE {temporary} AS
                    SELECT
                      ?::INTEGER AS decision_year,
                      simulation_year AS source_simulation_year,
                      scenario_id,
                      plan_design_id,
                      employee_id,
                      employee_ssn,
                      employee_birth_date,
                      employee_hire_date,
                      current_compensation,
                      full_year_equivalent_compensation,
                      current_age,
                      current_tenure,
                      level_id,
                      employment_status,
                      termination_date,
                      scheduled_hours_per_week
                    FROM int_workforce_state_accumulator
                    WHERE scenario_id = ?
                      AND plan_design_id = ?
                      AND simulation_year = ? - 1
                    ORDER BY employee_id
                    """,
                    [decision_year, scenario_id, plan_design_id, decision_year],
                )
            else:
                definitions = ", ".join(
                    f"{name} {data_type.replace(' NOT NULL', '')}"
                    for name, data_type in self._columns.items()
                )
                connection.execute(f"CREATE TABLE {temporary} ({definitions})")
            duplicates = connection.execute(
                f"SELECT COUNT(*) - COUNT(DISTINCT employee_id) FROM {temporary}"
            ).fetchone()[0]
            if duplicates:
                raise RuntimeError("Workforce projection contains duplicate employees")
            connection.execute(f"DROP TABLE IF EXISTS {self.table_name}")
            connection.execute(f"ALTER TABLE {temporary} RENAME TO {self.table_name}")
            return connection.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

        count = self.db_manager.execute_with_retry(_rebuild, deterministic=True)
        logger.info(
            "Rebuilt workforce projection for year %d (%s/%s): %d employees",
            decision_year,
            scenario_id,
            plan_design_id,
            count,
        )
        return WorkforceProjectionResult(
            decision_year=decision_year,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            employee_count=count,
        )
