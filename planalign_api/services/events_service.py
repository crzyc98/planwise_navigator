"""Read-only paginated access to scenario yearly events."""

from contextlib import contextmanager
from typing import Iterator

import duckdb

from ..models.events import EventListResponse, EventRecord
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    create_api_database_path_resolver,
)


class EventExplorerDatabaseNotFoundError(LookupError):
    """Raised when a scenario has no resolvable results database."""


class EventExplorerService:
    """Retrieve yearly events without mutation."""

    _FIELDS = (
        "event_id",
        "event_type",
        "event_category",
        "event_sequence",
        "effective_date",
        "simulation_year",
        "employee_id",
        "employee_ssn",
        "employee_age",
        "employee_tenure",
        "level_id",
        "age_band",
        "tenure_band",
        "scenario_id",
        "plan_design_id",
        "event_details",
        "compensation_amount",
        "previous_compensation",
        "employee_deferral_rate",
        "prev_employee_deferral_rate",
        "event_probability",
        "parameter_scenario_id",
        "parameter_source",
        "data_quality_flag",
        "created_at",
    )

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
    ) -> Iterator[tuple[duckdb.DuckDBPyConnection, ResolvedDatabasePath]]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists or resolved.path is None:
            raise EventExplorerDatabaseNotFoundError(
                f"Scenario {scenario_id} has no results database"
            )
        connection = duckdb.connect(str(resolved.path), read_only=True)
        try:
            yield connection, resolved
        finally:
            connection.close()

    def list_events(
        self,
        workspace_id: str,
        scenario_id: str,
        *,
        simulation_year: int | None = None,
        event_type: str | None = None,
        event_category: str | None = None,
        employee_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> EventListResponse:
        """Return a deterministically ordered page of yearly events."""
        predicates = ["1=1"]
        parameters: list[object] = []
        filters = (
            (simulation_year is not None, "simulation_year = ?", simulation_year),
            (event_type is not None, "LOWER(event_type) = LOWER(?)", event_type),
            (
                event_category is not None,
                "LOWER(event_category) = LOWER(?)",
                event_category,
            ),
            (employee_id is not None, "UPPER(employee_id) = UPPER(?)", employee_id),
        )
        for enabled, clause, value in filters:
            if enabled:
                predicates.append(clause)
                parameters.append(value)
        where = " AND ".join(predicates)
        columns = ", ".join(self._FIELDS)

        with self._connect(workspace_id, scenario_id) as (connection, resolved):
            total_row = connection.execute(
                f"SELECT COUNT(*) FROM fct_yearly_events WHERE {where}", parameters
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT {columns}
                FROM fct_yearly_events
                WHERE {where}
                ORDER BY simulation_year, effective_date, event_sequence, event_id
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()

        return EventListResponse(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            run_id=resolved.run_id,
            database_source=resolved.source,
            events=[EventRecord(**dict(zip(self._FIELDS, row))) for row in rows],
            total=total_row[0] if total_row else 0,
            page=page,
            page_size=page_size,
        )
