"""Voluntary-enrollment deferral segment analysis service.

Derives the observed average deferral rate for each age x income segment the
voluntary enrollment model uses, so an analyst can align new-hire deferral
assumptions with what the census actually shows.

Only participants (deferral rate above zero) are averaged. The configured
`demographic_base_rates` are the rate assigned to an employee *given that they
enroll*; whether they enroll at all is modeled separately by the enrollment
probability and opt-out rates. Averaging non-participants in would double-count
non-participation and bias every segment downward.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb

from ..models.deferral_segments import (
    DeferralSegment,
    DeferralSegmentAnalysisResult,
)
from .census_as_of import resolve_as_of_date
from .sql_security import (
    CENSUS_BIRTH_DATE_COLUMNS,
    CENSUS_COMPENSATION_COLUMNS,
    CENSUS_DEFERRAL_COLUMNS,
    CENSUS_HIRE_DATE_COLUMNS,
    CENSUS_TERMINATION_DATE_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
)

logger = logging.getLogger(__name__)

# Segments with fewer participants than this are flagged as low-confidence.
LOW_CONFIDENCE_THRESHOLD = 20

# Age and income boundaries must stay in lockstep with the `demographic_segmentation`
# CTE in dbt/models/intermediate/int_voluntary_enrollment_decision.sql. A suggestion
# computed on different cut points would silently not describe the segment it fills.
_AGE_SEGMENT_SQL = """
    CASE
      WHEN age < 31 THEN 'young'
      WHEN age < 46 THEN 'mid_career'
      WHEN age < 56 THEN 'mature'
      ELSE 'senior'
    END
"""

_INCOME_SEGMENT_SQL = """
    CASE
      WHEN compensation < 50000 THEN 'low'
      WHEN compensation < 100000 THEN 'moderate'
      WHEN compensation < 200000 THEN 'high'
      ELSE 'executive'
    END
"""


class DeferralSegmentAnalysisService:
    """Analyzes census data to derive per-segment deferral rate suggestions."""

    def __init__(self, workspaces_root: Path) -> None:
        self.workspaces_root = workspaces_root

    def analyze_deferral_segments(
        self,
        workspace_id: str,
        file_path: str,
        as_of_date: Optional[date] = None,
    ) -> DeferralSegmentAnalysisResult:
        """Analyze census data for per-segment average participant deferral rates.

        Args:
            workspace_id: Workspace identifier (used for relative path resolution).
            file_path: Path to census file. Absolute paths are used as-is;
                relative paths are resolved under workspaces_root/workspace_id.
            as_of_date: Date ages are measured at. Inferred from the census when
                omitted, matching the age/tenure band analyzers.

        Returns:
            DeferralSegmentAnalysisResult with one entry per populated segment.

        Raises:
            ValueError: If the file is not found, the format is unsupported, or
                required census columns are absent.
        """
        resolved = self._resolve_path(workspace_id, file_path)

        try:
            safe_path = validate_file_path_for_sql(
                resolved, [self.workspaces_root], context="census file"
            )
        except SQLSecurityError as exc:
            raise ValueError(str(exc)) from exc

        conn = duckdb.connect(":memory:")
        try:
            self._load_file(conn, safe_path, resolved.suffix.lower())
            columns = self._census_columns(conn)
            birth_col = self._require_column(
                columns, CENSUS_BIRTH_DATE_COLUMNS, "birth date"
            )
            comp_col = self._require_column(
                columns, CENSUS_COMPENSATION_COLUMNS, "compensation"
            )
            deferral_col = self._require_column(
                columns, CENSUS_DEFERRAL_COLUMNS, "deferral rate"
            )
            hire_col = self._optional_column(columns, CENSUS_HIRE_DATE_COLUMNS)
            term_col = self._optional_column(columns, CENSUS_TERMINATION_DATE_COLUMNS)

            resolved_as_of = resolve_as_of_date(conn, hire_col, term_col, as_of_date)

            return self._compute_result(
                conn,
                birth_col=birth_col,
                comp_col=comp_col,
                deferral_col=deferral_col,
                active_filter=self._active_filter(columns),
                as_of=resolved_as_of.date,
                as_of_source=resolved_as_of.source,
                source_file=file_path,
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

    def _census_columns(self, conn: duckdb.DuckDBPyConnection) -> set[str]:
        return {
            row[0].lower()
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'census'"
            ).fetchall()
        }

    def _require_column(
        self, existing: set[str], allowed: frozenset[str], label: str
    ) -> str:
        column = self._optional_column(existing, allowed)
        if column is None:
            expected = ", ".join(sorted(allowed))
            raise ValueError(
                f"No {label} column found in census. Expected one of: {expected}"
            )
        return column

    def _optional_column(
        self, existing: set[str], allowed: frozenset[str]
    ) -> Optional[str]:
        # Canonical `employee_*` names win over aliases, so a census carrying both
        # (say `employee_gross_compensation` and `annual_salary`) resolves to the
        # column the rest of the engine reads rather than whichever sorts first.
        preferred = sorted(
            allowed, key=lambda col: (not col.startswith("employee_"), col)
        )
        column = next((col for col in preferred if col in existing), None)
        if column is None:
            return None
        return validate_column_name_from_set(column, set(allowed), "census column")

    def _active_filter(self, columns: set[str]) -> str:
        """Return a SQL WHERE fragment that filters to active employees."""
        if "active" not in columns:
            return "1=1"
        return (
            "(active IS NULL "
            "OR UPPER(CAST(active AS VARCHAR)) IN ('ACTIVE', 'Y', '1', 'TRUE', 'YES'))"
        )

    def _compute_result(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        birth_col: str,
        comp_col: str,
        deferral_col: str,
        active_filter: str,
        as_of: date,
        as_of_source: str,
        source_file: str,
    ) -> DeferralSegmentAnalysisResult:
        conn.execute(
            f"""
            CREATE TABLE analyzed AS
            WITH base AS (
              SELECT
                FLOOR(
                  DATEDIFF('day', TRY_CAST({birth_col} AS DATE), ?::DATE) / 365.25
                ) AS age,
                TRY_CAST({comp_col} AS DOUBLE) AS compensation,
                TRY_CAST({deferral_col} AS DOUBLE) AS deferral_rate
              FROM census
              WHERE {active_filter}
            )
            SELECT
              {_AGE_SEGMENT_SQL} AS age_segment,
              {_INCOME_SEGMENT_SQL} AS income_segment,
              deferral_rate
            FROM base
            WHERE age IS NOT NULL AND age >= 18 AND age < 100
              AND compensation IS NOT NULL AND compensation >= 0
              -- Census deferral is a decimal fraction (stg_census_data casts it to
              -- DECIMAL(7,5)); anything above 1.0 is a percent-encoded or corrupt
              -- value that would otherwise inflate the segment average.
              AND deferral_rate IS NOT NULL
              AND deferral_rate >= 0
              AND deferral_rate <= 1
            """,
            [as_of],
        )

        total_active = self._scalar(
            conn, f"SELECT COUNT(*) FROM census WHERE {active_filter}"
        )
        total_analyzed = self._scalar(conn, "SELECT COUNT(*) FROM analyzed")
        total_participants = self._scalar(
            conn, "SELECT COUNT(*) FROM analyzed WHERE deferral_rate > 0"
        )
        overall_average = self._scalar(
            conn, "SELECT AVG(deferral_rate) FROM analyzed WHERE deferral_rate > 0"
        )

        rows = conn.execute(
            """
            SELECT
              age_segment,
              income_segment,
              COUNT(*) AS employee_count,
              COUNT(*) FILTER (WHERE deferral_rate > 0) AS participant_count,
              AVG(deferral_rate) FILTER (WHERE deferral_rate > 0) AS average_deferral_rate
            FROM analyzed
            GROUP BY age_segment, income_segment
            ORDER BY age_segment, income_segment
            """
        ).fetchall()

        segments = [
            DeferralSegment(
                segment=f"{age_segment}_{income_segment}",
                age_segment=age_segment,
                income_segment=income_segment,
                average_deferral_rate=average,
                participant_count=participant_count,
                employee_count=employee_count,
                low_confidence=participant_count < LOW_CONFIDENCE_THRESHOLD,
            )
            for age_segment, income_segment, employee_count, participant_count, average in rows
        ]

        return DeferralSegmentAnalysisResult(
            segments=segments,
            total_employees_analyzed=total_analyzed,
            total_participants=total_participants,
            overall_average_deferral_rate=overall_average,
            excluded_count=total_active - total_analyzed,
            as_of_date=as_of,
            as_of_date_source=as_of_source,
            low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
            source_file=source_file,
            message=self._message(total_analyzed, total_participants, segments),
        )

    def _scalar(self, conn: duckdb.DuckDBPyConnection, sql: str):
        row = conn.execute(sql).fetchone()
        return row[0] if row else None

    def _message(
        self,
        total_analyzed: int,
        total_participants: int,
        segments: list[DeferralSegment],
    ) -> Optional[str]:
        if total_analyzed == 0:
            return (
                "No employees with usable age, compensation, and deferral values were "
                "found in the census."
            )
        if total_participants == 0:
            return (
                "No census employees have a deferral rate above zero, so no segment "
                "average could be computed."
            )
        low_confidence = [s.segment for s in segments if s.low_confidence]
        if low_confidence:
            return (
                f"{len(low_confidence)} segment(s) have fewer than "
                f"{LOW_CONFIDENCE_THRESHOLD} participants and may not be reliable: "
                f"{', '.join(low_confidence)}."
            )
        return None
