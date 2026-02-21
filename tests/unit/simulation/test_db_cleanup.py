"""Tests for db_cleanup module."""

import pytest
import duckdb
from pathlib import Path

from planalign_api.services.simulation.db_cleanup import (
    cleanup_years_outside_range,
    TABLES_WITH_YEAR,
)


@pytest.mark.fast
class TestCleanupYearsOutsideRange:
    """Test cleanup_years_outside_range function."""

    def _create_db_with_table(self, tmp_path: Path) -> Path:
        """Create a DuckDB file with a table containing simulation_year data."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE fct_workforce_snapshot (
                employee_id VARCHAR,
                simulation_year INTEGER
            )
        """
        )
        conn.execute(
            """
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP1', 2024), ('EMP2', 2025), ('EMP3', 2026),
                ('EMP4', 2027), ('EMP5', 2028)
        """
        )
        conn.close()
        return db_path

    def test_deletes_rows_outside_range(self, tmp_path):
        """Should delete rows with years outside start-end range."""
        db_path = self._create_db_with_table(tmp_path)

        result = cleanup_years_outside_range(db_path, 2025, 2027)

        assert "fct_workforce_snapshot" in result
        assert result["fct_workforce_snapshot"] == 2  # 2024 and 2028

        conn = duckdb.connect(str(db_path), read_only=True)
        remaining = conn.execute(
            "SELECT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year"
        ).fetchall()
        conn.close()

        assert [r[0] for r in remaining] == [2025, 2026, 2027]

    def test_no_deletions_when_all_in_range(self, tmp_path):
        """Should return empty dict when all data is within range."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot (employee_id VARCHAR, simulation_year INTEGER)"
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot VALUES ('EMP1', 2025), ('EMP2', 2026)"
        )
        conn.close()

        result = cleanup_years_outside_range(db_path, 2025, 2027)

        assert result == {}

    def test_handles_missing_db(self, tmp_path):
        """Should not raise when database does not exist."""
        db_path = tmp_path / "nonexistent.duckdb"
        result = cleanup_years_outside_range(db_path, 2025, 2027)
        assert result == {}

    def test_skips_tables_without_year_column(self, tmp_path):
        """Should skip tables that lack simulation_year column."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot (employee_id VARCHAR, name VARCHAR)"
        )
        conn.execute("INSERT INTO fct_workforce_snapshot VALUES ('EMP1', 'Alice')")
        conn.close()

        result = cleanup_years_outside_range(db_path, 2025, 2027)
        assert result == {}

    def test_skips_nonexistent_tables(self, tmp_path):
        """Should skip tables that don't exist in the database."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
        conn.close()

        result = cleanup_years_outside_range(db_path, 2025, 2027)
        assert result == {}

    def test_tables_with_year_list_is_nonempty(self):
        """Sanity check that the table list is defined."""
        assert len(TABLES_WITH_YEAR) > 0
        assert "fct_workforce_snapshot" in TABLES_WITH_YEAR
