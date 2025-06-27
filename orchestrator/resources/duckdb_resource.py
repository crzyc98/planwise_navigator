"""DuckDB resource for Dagster."""

from dagster import ConfigurableResource, get_dagster_logger
import duckdb
from typing import Optional


class DuckDBResource(ConfigurableResource):
    """Resource for connecting to DuckDB with automatic Parquet extension loading."""

    database_path: Optional[str] = None
    read_only: bool = False

    def get_connection(self):
        """Get a DuckDB connection with Parquet extension automatically loaded."""
        logger = get_dagster_logger()

        conn = duckdb.connect(
            database=self.database_path if self.database_path else ":memory:",
            read_only=self.read_only,
        )

        try:
            # Try to load Parquet extension (should work if installed globally)
            conn.execute("LOAD parquet;")
            logger.debug("Parquet extension loaded successfully")
        except Exception as load_error:
            # If loading fails, log warning but don't try to install to avoid network issues
            logger.warning(f"Parquet extension not available: {load_error}")
            logger.info("Run 'python scripts/setup_duckdb_extensions.py' to install extensions")
            # Continue without failing - some operations may not need Parquet

        return conn
