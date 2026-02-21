"""Turnover rate analysis service.

Analyzes census data to suggest experienced and new hire termination rates
based on actual employee termination history.
"""

import logging
from datetime import date
from pathlib import Path

import duckdb

from ..models.turnover import TurnoverAnalysisResult, TurnoverRateSuggestion
from .sql_security import (
    CENSUS_HIRE_DATE_COLUMNS,
    CENSUS_TERMINATION_DATE_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
)

logger = logging.getLogger(__name__)


class TurnoverAnalysisService:
    """Analyzes census data to derive termination rate suggestions."""

    def __init__(self, workspaces_root: Path):
        self.workspaces_root = workspaces_root

    def analyze_turnover_rates(
        self, workspace_id: str, file_path: str
    ) -> TurnoverAnalysisResult:
        """
        Analyze census data to suggest termination rates.

        Calculates:
        - Experienced termination rate: terminated employees with tenure >= 1 year / total experienced
        - New hire termination rate: terminated employees with tenure < 1 year / total new hires

        Args:
            workspace_id: Workspace ID
            file_path: Path to census file (relative to workspace or absolute)

        Returns:
            TurnoverAnalysisResult with suggested rates and statistics
        """
        # Resolve file path
        if file_path.startswith("/"):
            resolved = Path(file_path)
        else:
            resolved = self.workspaces_root / workspace_id / file_path

        if not resolved.exists():
            raise ValueError(f"File not found: {file_path}")

        # Validate file path for SQL safety
        try:
            safe_path = validate_file_path_for_sql(
                resolved, [self.workspaces_root], context="census file"
            )
        except SQLSecurityError as e:
            raise ValueError(str(e))

        # Read the file using DuckDB
        suffix = resolved.suffix.lower()
        conn = duckdb.connect(":memory:")

        try:
            if suffix == ".parquet":
                conn.execute(
                    f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')"
                )
            elif suffix == ".csv":
                conn.execute(
                    f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)"
                )
            else:
                conn.close()
                raise ValueError(f"Unsupported file type: {suffix}")

            # Get column names
            columns_result = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'census'"
            ).fetchall()
            columns = [row[0] for row in columns_result]

            # Find hire date column (required)
            hire_date_col = None
            for col_name in CENSUS_HIRE_DATE_COLUMNS:
                if col_name in columns:
                    hire_date_col = validate_column_name_from_set(
                        col_name, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
                    )
                    break

            if not hire_date_col:
                raise ValueError(
                    "Census file must contain a hire date column "
                    "(employee_hire_date, hire_date, hiredate, or start_date)"
                )

            # Find termination date column
            term_date_col = None
            for col_name in CENSUS_TERMINATION_DATE_COLUMNS:
                if col_name in columns:
                    term_date_col = validate_column_name_from_set(
                        col_name, CENSUS_TERMINATION_DATE_COLUMNS, "termination date column"
                    )
                    break

            # Determine termination status
            has_active_col = "active" in columns
            has_status_col = "status" in columns

            if not term_date_col and not has_active_col and not has_status_col:
                raise ValueError(
                    "Census file must contain termination data. Expected one of: "
                    "employee_termination_date/termination_date/term_date column, "
                    "or an 'active' boolean column, or a 'status' column."
                )

            today = date.today()
            today_str = today.isoformat()

            # Add computed columns for tenure and termination status
            conn.execute("ALTER TABLE census ADD COLUMN _tenure_years DOUBLE")
            conn.execute(
                f"""
                UPDATE census SET _tenure_years =
                    DATEDIFF('day', CAST({hire_date_col} AS DATE), ?::DATE) / 365.25
                """,
                [today_str],
            )

            # Remove rows with invalid tenure
            conn.execute("DELETE FROM census WHERE _tenure_years < 0 OR _tenure_years IS NULL")

            # Determine terminated status
            conn.execute("ALTER TABLE census ADD COLUMN _is_terminated BOOLEAN DEFAULT false")

            if term_date_col:
                # Primary: use termination date column
                conn.execute(
                    f"""
                    UPDATE census SET _is_terminated = true
                    WHERE {term_date_col} IS NOT NULL
                      AND CAST({term_date_col} AS VARCHAR) != ''
                    """
                )
            elif has_active_col:
                # Fallback: use active boolean column
                conn.execute(
                    "UPDATE census SET _is_terminated = true WHERE active = false"
                )
            elif has_status_col:
                # Fallback: use status column
                conn.execute(
                    "UPDATE census SET _is_terminated = true WHERE LOWER(status) != 'active'"
                )

            # If we have both term_date and active columns, also check active=false
            if term_date_col and has_active_col:
                conn.execute(
                    "UPDATE census SET _is_terminated = true WHERE active = false"
                )

            # Calculate totals
            total_employees = conn.execute(
                "SELECT COUNT(*) FROM census"
            ).fetchone()[0]

            total_terminated = conn.execute(
                "SELECT COUNT(*) FROM census WHERE _is_terminated = true"
            ).fetchone()[0]

            if total_employees == 0:
                raise ValueError("No employees with valid data found in census file")

            # Handle case where no terminated employees found
            if total_terminated == 0:
                return TurnoverAnalysisResult(
                    experienced_rate=None,
                    new_hire_rate=None,
                    total_employees=total_employees,
                    total_terminated=0,
                    analysis_type="All employees",
                    source_file=str(file_path),
                    message=(
                        "No terminated employees found in census data. "
                        "All employees appear to be active. "
                        "Consider using industry-standard defaults "
                        "(12% experienced, 25% new hire)."
                    ),
                )

            # Split into experienced (tenure >= 1 year) and new hires (tenure < 1 year)
            stats = conn.execute(
                """
                SELECT
                    -- Experienced employees (tenure >= 1 year)
                    COUNT(*) FILTER (WHERE _tenure_years >= 1) AS experienced_total,
                    COUNT(*) FILTER (WHERE _tenure_years >= 1 AND _is_terminated) AS experienced_terminated,
                    -- New hires (tenure < 1 year)
                    COUNT(*) FILTER (WHERE _tenure_years < 1) AS new_hire_total,
                    COUNT(*) FILTER (WHERE _tenure_years < 1 AND _is_terminated) AS new_hire_terminated
                FROM census
                """
            ).fetchone()

            experienced_total = stats[0]
            experienced_terminated = stats[1]
            new_hire_total = stats[2]
            new_hire_terminated = stats[3]

            # Build experienced rate suggestion
            experienced_rate = None
            if experienced_total > 0 and experienced_terminated > 0:
                rate = experienced_terminated / experienced_total
                experienced_rate = TurnoverRateSuggestion(
                    rate=round(rate, 4),
                    sample_size=experienced_total,
                    terminated_count=experienced_terminated,
                    confidence=_confidence_level(experienced_terminated),
                )

            # Build new hire rate suggestion
            new_hire_rate = None
            if new_hire_total > 0 and new_hire_terminated > 0:
                rate = new_hire_terminated / new_hire_total
                new_hire_rate = TurnoverRateSuggestion(
                    rate=round(rate, 4),
                    sample_size=new_hire_total,
                    terminated_count=new_hire_terminated,
                    confidence=_confidence_level(new_hire_terminated),
                )

            # Build message for edge cases
            message = None
            messages = []
            if new_hire_total == 0:
                messages.append(
                    "No employees with tenure < 1 year found; "
                    "cannot derive new hire termination rate."
                )
            elif new_hire_terminated == 0:
                messages.append(
                    "No terminated new hires found; "
                    "cannot derive new hire termination rate."
                )
            if experienced_total > 0 and experienced_terminated == 0:
                messages.append(
                    "No terminated experienced employees found; "
                    "cannot derive experienced termination rate."
                )
            if messages:
                message = " ".join(messages)

            return TurnoverAnalysisResult(
                experienced_rate=experienced_rate,
                new_hire_rate=new_hire_rate,
                total_employees=total_employees,
                total_terminated=total_terminated,
                analysis_type="All employees",
                source_file=str(file_path),
                message=message,
            )

        finally:
            conn.close()


def _confidence_level(terminated_count: int) -> str:
    """Determine confidence level based on sample size of terminated employees."""
    if terminated_count >= 30:
        return "high"
    elif terminated_count >= 10:
        return "moderate"
    else:
        return "low"
