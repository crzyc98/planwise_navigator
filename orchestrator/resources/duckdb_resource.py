"""DuckDB resource for Dagster."""

from dagster import ConfigurableResource
import duckdb
from typing import Optional


class DuckDBResource(ConfigurableResource):
    """Resource for connecting to DuckDB."""

    database_path: Optional[str] = None
    read_only: bool = False

    def get_connection(self):
        """Get a DuckDB connection."""
        return duckdb.connect(
            database=self.database_path if self.database_path else ":memory:",
            read_only=self.read_only,
        )
