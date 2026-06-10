"""Opt-out rate analysis service.

Analyzes census data to suggest a target opt-out rate based on the
non-participant rate among recently hired employees.
"""

import logging
from pathlib import Path

import duckdb

from ..models.opt_out import OptOutRateAnalysisResult
from .sql_security import (
    CENSUS_DEFERRAL_COLUMNS,
    CENSUS_HIRE_DATE_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
)

logger = logging.getLogger(__name__)

# Employees with fewer than this many records in the lookback window are flagged as low-confidence.
_LOW_CONFIDENCE_THRESHOLD = 20


class OptOutAnalysisService:
    """Analyzes census data to derive opt-out rate suggestions."""

    def __init__(self, workspaces_root: Path) -> None:
        self.workspaces_root = workspaces_root

    def analyze_opt_out_rate(
        self, workspace_id: str, file_path: str, lookback_years: int = 3
    ) -> OptOutRateAnalysisResult:
        """Analyze census data to suggest a target opt-out rate.

        Filters to active employees hired within *lookback_years* of the most
        recent hire date in the census, then calculates the fraction who have
        no active deferral (deferral_rate = 0 or NULL).

        Args:
            workspace_id: Workspace identifier (used for relative path resolution).
            file_path: Path to census file. Absolute paths are used as-is;
                relative paths are resolved under workspaces_root/workspace_id.
            lookback_years: Only include employees hired within this many years
                of MAX(hire_date) in the census. Default 3.

        Returns:
            OptOutRateAnalysisResult with suggested rate and supporting statistics.

        Raises:
            ValueError: If the file is not found, the format is unsupported,
                or required census columns are absent.
        """
        resolved = self._resolve_path(workspace_id, file_path)

        try:
            safe_path = validate_file_path_for_sql(
                resolved, [self.workspaces_root], context="census file"
            )
        except SQLSecurityError as exc:
            raise ValueError(str(exc)) from exc

        suffix = resolved.suffix.lower()
        conn = duckdb.connect(":memory:")
        try:
            self._load_file(conn, safe_path, suffix)
            hire_col, deferral_col = self._detect_columns(conn)
            return self._compute_result(
                conn, hire_col, deferral_col, lookback_years, file_path
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, workspace_id: str, file_path: str) -> Path:
        if file_path.startswith("/"):
            resolved = Path(file_path)
        else:
            resolved = self.workspaces_root / workspace_id / file_path
        if not resolved.exists():
            raise ValueError(f"File not found: {file_path}")
        return resolved

    def _load_file(
        self, conn: duckdb.DuckDBPyConnection, safe_path: str, suffix: str
    ) -> None:
        if suffix == ".parquet":
            conn.execute(
                f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')"
            )
        elif suffix == ".csv":
            conn.execute(
                f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)"
            )
        else:
            raise ValueError(
                f"Unsupported file type: {suffix}. Expected .csv or .parquet"
            )

    def _detect_columns(self, conn: duckdb.DuckDBPyConnection) -> tuple[str, str]:
        """Return (hire_date_col, deferral_col) detected in the census table."""
        existing = {
            row[0].lower()
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'census'"
            ).fetchall()
        }

        hire_col = next(
            (col for col in CENSUS_HIRE_DATE_COLUMNS if col.lower() in existing), None
        )
        if hire_col is None:
            expected = ", ".join(sorted(CENSUS_HIRE_DATE_COLUMNS))
            raise ValueError(
                f"No hire date column found in census. Expected one of: {expected}"
            )

        deferral_col = next(
            (col for col in CENSUS_DEFERRAL_COLUMNS if col.lower() in existing), None
        )
        if deferral_col is None:
            expected = ", ".join(sorted(CENSUS_DEFERRAL_COLUMNS))
            raise ValueError(
                f"No deferral rate column found in census. Expected one of: {expected}"
            )

        # Validate against the allowlist before use in SQL
        validate_column_name_from_set(
            hire_col, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
        )
        validate_column_name_from_set(
            deferral_col, CENSUS_DEFERRAL_COLUMNS, "deferral rate column"
        )

        return hire_col, deferral_col

    def _compute_result(
        self,
        conn: duckdb.DuckDBPyConnection,
        hire_col: str,
        deferral_col: str,
        lookback_years: int,
        source_file: str,
    ) -> OptOutRateAnalysisResult:
        # Identify active-employee indicator column if present
        active_filter = self._active_filter(conn)

        # Count employees with NULL hire_date (excluded from all calculations)
        excluded_null_tenure = conn.execute(
            f"SELECT COUNT(*) FROM census WHERE {active_filter} AND ({hire_col} IS NULL OR CAST({hire_col} AS VARCHAR) = '')"
        ).fetchone()[0]

        # Total eligible (active, non-null hire date)
        total_eligible_in_census = conn.execute(
            f"SELECT COUNT(*) FROM census WHERE {active_filter} AND {hire_col} IS NOT NULL AND CAST({hire_col} AS VARCHAR) != ''"
        ).fetchone()[0]

        # Lookback cutoff: MAX(hire_date) - lookback_years * 365 days
        max_hire_row = conn.execute(
            f"SELECT MAX(TRY_CAST({hire_col} AS DATE)) FROM census WHERE {active_filter} AND {hire_col} IS NOT NULL AND CAST({hire_col} AS VARCHAR) != ''"
        ).fetchone()
        if max_hire_row is None or max_hire_row[0] is None:
            return self._empty_result(
                hire_col, lookback_years, source_file, excluded_null_tenure
            )

        cutoff_sql = f"(MAX(TRY_CAST({hire_col} AS DATE)) - INTERVAL {lookback_years * 365} DAYS)"

        eligible_count = conn.execute(
            f"""
            SELECT COUNT(*) FROM census
            WHERE {active_filter}
              AND TRY_CAST({hire_col} AS DATE) IS NOT NULL
              AND TRY_CAST({hire_col} AS DATE) >= (
                  SELECT MAX(TRY_CAST({hire_col} AS DATE)) - INTERVAL {lookback_years * 365} DAYS
                  FROM census
                  WHERE {active_filter} AND {hire_col} IS NOT NULL AND CAST({hire_col} AS VARCHAR) != ''
              )
            """
        ).fetchone()[0]

        if eligible_count == 0:
            return OptOutRateAnalysisResult(
                suggested_rate=None,
                eligible_count=0,
                non_participant_count=0,
                total_eligible_in_census=total_eligible_in_census,
                excluded_null_tenure=excluded_null_tenure,
                lookback_years=lookback_years,
                hire_date_column_used=hire_col,
                analysis_type=f"Non-participant rate for employees hired within last {lookback_years} year(s)",
                source_file=source_file,
                message=(
                    f"No eligible employees found within the {lookback_years}-year lookback window. "
                    "Try a longer lookback."
                ),
            )

        non_participant_count = conn.execute(
            f"""
            SELECT COUNT(*) FROM census
            WHERE {active_filter}
              AND TRY_CAST({hire_col} AS DATE) IS NOT NULL
              AND TRY_CAST({hire_col} AS DATE) >= (
                  SELECT MAX(TRY_CAST({hire_col} AS DATE)) - INTERVAL {lookback_years * 365} DAYS
                  FROM census
                  WHERE {active_filter} AND {hire_col} IS NOT NULL AND CAST({hire_col} AS VARCHAR) != ''
              )
              AND (TRY_CAST({deferral_col} AS DOUBLE) IS NULL
                   OR TRY_CAST({deferral_col} AS DOUBLE) = 0)
            """
        ).fetchone()[0]

        suggested_rate = non_participant_count / eligible_count

        message = None
        if eligible_count < _LOW_CONFIDENCE_THRESHOLD:
            message = (
                f"Small sample — only {eligible_count} employee(s) in the {lookback_years}-year "
                "window. Consider a longer lookback for a more reliable estimate."
            )

        return OptOutRateAnalysisResult(
            suggested_rate=suggested_rate,
            eligible_count=eligible_count,
            non_participant_count=non_participant_count,
            total_eligible_in_census=total_eligible_in_census,
            excluded_null_tenure=excluded_null_tenure,
            lookback_years=lookback_years,
            hire_date_column_used=hire_col,
            analysis_type=f"Non-participant rate for employees hired within last {lookback_years} year(s)",
            source_file=source_file,
            message=message,
        )

    def _active_filter(self, conn: duckdb.DuckDBPyConnection) -> str:
        """Return a SQL WHERE fragment that filters to active employees.

        If no 'active' column exists, defaults to including all rows.
        """
        columns = {
            row[0].lower()
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'census'"
            ).fetchall()
        }
        if "active" not in columns:
            return "1=1"
        return (
            "(active IS NULL "
            "OR UPPER(CAST(active AS VARCHAR)) IN ('ACTIVE', 'Y', '1', 'TRUE', 'YES'))"
        )

    def _empty_result(
        self,
        hire_col: str,
        lookback_years: int,
        source_file: str,
        excluded_null_tenure: int,
    ) -> OptOutRateAnalysisResult:
        return OptOutRateAnalysisResult(
            suggested_rate=None,
            eligible_count=0,
            non_participant_count=0,
            total_eligible_in_census=0,
            excluded_null_tenure=excluded_null_tenure,
            lookback_years=lookback_years,
            hire_date_column_used=hire_col,
            analysis_type=f"Non-participant rate for employees hired within last {lookback_years} year(s)",
            source_file=source_file,
            message="No eligible employees found in the census.",
        )
