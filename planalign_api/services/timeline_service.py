"""Read-only queries for an employee's event-sourced storyline."""

from contextlib import contextmanager
from typing import Iterator

import duckdb

from ..models.timeline import (
    EmployeeIdentity,
    EmployeeSearchResponse,
    EmployeeSearchResult,
    EmployeeTimelineResponse,
    TimelineEvent,
    TimelineYear,
    YearState,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)


class TimelineDatabaseNotFoundError(LookupError):
    """Raised when a scenario has no resolvable results database."""


class TimelineService:
    """Retrieve merged timeline events and year-end state without mutation."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: DatabasePathResolver | None = None,
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    @contextmanager
    def _connect(
        self, workspace_id: str, scenario_id: str
    ) -> Iterator[duckdb.DuckDBPyConnection]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists or resolved.path is None:
            raise TimelineDatabaseNotFoundError(
                f"Scenario {scenario_id} has no results database"
            )
        connection = duckdb.connect(str(resolved.path), read_only=True)
        try:
            yield connection
        finally:
            connection.close()

    def get_timeline(
        self,
        workspace_id: str,
        scenario_id: str,
        employee_id: str,
        start_year: int | None = None,
        years: int = 3,
    ) -> EmployeeTimelineResponse:
        """Return a year-paginated timeline, oldest first."""
        normalized = employee_id.strip()
        with self._connect(workspace_id, scenario_id) as connection:
            canonical = self._canonical_employee_id(connection, normalized)
            if canonical is None:
                return EmployeeTimelineResponse(
                    workspace_id=workspace_id,
                    scenario_id=scenario_id,
                    employee_id=normalized,
                    employee=None,
                    available_years=[],
                    years=[],
                    start_year=start_year or 0,
                    years_requested=years,
                )
            available_years = self._available_years(connection, canonical)
            page_start = start_year if start_year is not None else available_years[0]
            page_years = [
                year
                for year in available_years
                if page_start <= year < page_start + years
            ]
            events = self._query_events(connection, canonical, page_years)
            states = self._query_states(connection, canonical, page_years)
            identity = self._query_identity(connection, canonical)

        grouped: dict[int, list[TimelineEvent]] = {year: [] for year in page_years}
        for event in events:
            grouped[event.simulation_year].append(event)
        return EmployeeTimelineResponse(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            employee_id=canonical,
            employee=identity or EmployeeIdentity(employee_id=canonical),
            available_years=available_years,
            years=[
                TimelineYear(
                    simulation_year=year, events=grouped[year], state=states.get(year)
                )
                for year in page_years
            ],
            start_year=page_start,
            years_requested=years,
        )

    def search_employees(
        self,
        workspace_id: str,
        scenario_id: str,
        q: str | None = None,
        status: str | None = None,
        level: int | None = None,
        year: int | None = None,
        enrolled: bool | None = None,
        has_escalations: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> EmployeeSearchResponse:
        """Search snapshot employees using composable, bound predicates."""
        with self._connect(workspace_id, scenario_id) as connection:
            max_year_row = connection.execute(
                "SELECT MAX(simulation_year) FROM fct_workforce_snapshot"
            ).fetchone()
            selected_year = year or (max_year_row[0] if max_year_row else None)
            predicates = ["simulation_year = ?"]
            parameters: list[object] = [selected_year]
            filters = [
                (
                    q is not None,
                    "UPPER(employee_id) LIKE UPPER(?) || '%'",
                    (q or "").strip(),
                ),
                (status is not None, "LOWER(employment_status) = LOWER(?)", status),
                (level is not None, "level_id = ?", level),
                (enrolled is not None, "is_enrolled_flag = ?", enrolled),
                (
                    has_escalations is not None,
                    "has_deferral_escalations = ?",
                    has_escalations,
                ),
            ]
            for enabled, clause, value in filters:
                if enabled:
                    predicates.append(clause)
                    parameters.append(value)
            where = " AND ".join(predicates)
            total_row = connection.execute(
                f"SELECT COUNT(DISTINCT employee_id) FROM fct_workforce_snapshot WHERE {where}",
                parameters,
            ).fetchone()
            total = total_row[0] if total_row else 0
            result_limit = (
                min(page_size, 20)
                if q is not None
                and not any(
                    value is not None
                    for value in (status, level, enrolled, has_escalations)
                )
                else page_size
            )
            rows = connection.execute(
                f"""
                SELECT employee_id, employment_status, level_id,
                       current_compensation, simulation_year
                FROM fct_workforce_snapshot
                WHERE {where}
                ORDER BY employee_id
                LIMIT ? OFFSET ?
                """,
                [*parameters, result_limit, (page - 1) * result_limit],
            ).fetchall()
        return EmployeeSearchResponse(
            results=[
                EmployeeSearchResult(
                    **dict(
                        zip(
                            (
                                "employee_id",
                                "employment_status",
                                "level_id",
                                "current_compensation",
                                "simulation_year",
                            ),
                            row,
                        )
                    )
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=result_limit,
        )

    @staticmethod
    def _canonical_employee_id(
        connection: duckdb.DuckDBPyConnection, employee_id: str
    ) -> str | None:
        row = connection.execute(
            """
            SELECT employee_id FROM (
              SELECT employee_id FROM fct_yearly_events
              UNION ALL SELECT employee_id FROM fct_employer_match_events
              UNION ALL SELECT employee_id FROM fct_workforce_snapshot
            ) WHERE UPPER(employee_id) = UPPER(?) ORDER BY employee_id LIMIT 1
            """,
            [employee_id],
        ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _available_years(
        connection: duckdb.DuckDBPyConnection, employee_id: str
    ) -> list[int]:
        rows = connection.execute(
            """
            SELECT DISTINCT simulation_year FROM (
              SELECT simulation_year FROM fct_yearly_events WHERE UPPER(employee_id) = UPPER(?)
              UNION ALL SELECT simulation_year FROM fct_employer_match_events WHERE UPPER(employee_id) = UPPER(?)
              UNION ALL SELECT simulation_year FROM fct_workforce_snapshot WHERE UPPER(employee_id) = UPPER(?)
            ) ORDER BY simulation_year
            """,
            [employee_id, employee_id, employee_id],
        ).fetchall()
        return [int(row[0]) for row in rows]

    @staticmethod
    def _query_events(
        connection: duckdb.DuckDBPyConnection, employee_id: str, years: list[int]
    ) -> list[TimelineEvent]:
        if not years:
            return []
        rows = connection.execute(
            """
            SELECT event_id, source, event_type, simulation_year, effective_date,
                   event_details, compensation_amount, previous_compensation,
                   deferral_rate, prev_deferral_rate, level_id
            FROM (
              SELECT CAST(event_id AS VARCHAR) AS event_id, 'yearly' AS source, event_type,
                simulation_year, effective_date, event_details, compensation_amount,
                previous_compensation, employee_deferral_rate AS deferral_rate,
                prev_employee_deferral_rate AS prev_deferral_rate, level_id,
                COALESCE(event_sequence, 999) AS event_sequence
              FROM fct_yearly_events WHERE UPPER(employee_id) = UPPER(?)
              UNION ALL
              SELECT CAST(event_id AS VARCHAR) AS event_id, 'employer_match' AS source, event_type,
                simulation_year, effective_date, CAST(event_payload AS VARCHAR), amount,
                NULL, employee_deferral_rate, NULL, NULL, 999
              FROM fct_employer_match_events WHERE UPPER(employee_id) = UPPER(?)
            )
            WHERE simulation_year >= ? AND simulation_year < ?
            ORDER BY simulation_year, effective_date, event_sequence, event_id
            """,
            [employee_id, employee_id, min(years), max(years) + 1],
        ).fetchall()
        fields = (
            "event_id",
            "source",
            "event_type",
            "simulation_year",
            "effective_date",
            "event_details",
            "compensation_amount",
            "previous_compensation",
            "deferral_rate",
            "prev_deferral_rate",
            "level_id",
        )
        return [TimelineEvent(**dict(zip(fields, row))) for row in rows]

    @staticmethod
    def _query_states(
        connection: duckdb.DuckDBPyConnection, employee_id: str, years: list[int]
    ) -> dict[int, YearState]:
        if not years:
            return {}
        rows = connection.execute(
            """
            SELECT simulation_year, employment_status, detailed_status_code,
              current_compensation, prorated_annual_compensation, level_id,
              current_age, current_tenure, current_eligibility_status,
              is_enrolled_flag, employee_enrollment_date, current_deferral_rate,
              participation_status, total_deferral_escalations, ytd_contributions,
              pre_tax_contributions, roth_contributions, employer_match_amount,
              employer_core_amount, total_employer_contributions, irs_limit_reached
            FROM fct_workforce_snapshot
            WHERE UPPER(employee_id) = UPPER(?) AND simulation_year >= ? AND simulation_year < ?
            ORDER BY simulation_year
            """,
            [employee_id, min(years), max(years) + 1],
        ).fetchall()
        fields = (
            "simulation_year",
            "employment_status",
            "detailed_status_code",
            "current_compensation",
            "prorated_annual_compensation",
            "level_id",
            "current_age",
            "current_tenure",
            "eligibility_status",
            "is_enrolled",
            "enrollment_date",
            "current_deferral_rate",
            "participation_status",
            "total_deferral_escalations",
            "ytd_contributions",
            "pre_tax_contributions",
            "roth_contributions",
            "employer_match_amount",
            "employer_core_amount",
            "total_employer_contributions",
            "irs_limit_reached",
        )
        states = [YearState(**dict(zip(fields, row))) for row in rows]
        return {state.simulation_year: state for state in states}

    @staticmethod
    def _query_identity(
        connection: duckdb.DuckDBPyConnection, employee_id: str
    ) -> EmployeeIdentity | None:
        row = connection.execute(
            """
            SELECT employee_id, employee_ssn, employee_birth_date, employee_hire_date
            FROM fct_workforce_snapshot WHERE UPPER(employee_id) = UPPER(?)
            ORDER BY simulation_year DESC LIMIT 1
            """,
            [employee_id],
        ).fetchone()
        if not row:
            return None
        return EmployeeIdentity(
            **dict(
                zip(
                    (
                        "employee_id",
                        "employee_ssn",
                        "employee_birth_date",
                        "employee_hire_date",
                    ),
                    row,
                )
            )
        )
