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
            # Try to load Parquet extension first
            conn.execute("LOAD parquet;")
            logger.debug("Parquet extension loaded successfully")
        except Exception as load_error:
            try:
                # If loading fails, try to install it first (one-time setup)
                logger.info(f"Parquet extension not loaded ({load_error}), attempting to install...")
                conn.execute("INSTALL parquet;")
                conn.execute("LOAD parquet;")
                logger.info("Parquet extension installed and loaded successfully")
            except Exception as install_error:
                logger.warning(f"Failed to install/load Parquet extension: {install_error}")
                # Continue without failing - some operations may not need Parquet

        return conn
