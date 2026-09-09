"""Pre-simulation census analysis service.

Computes the same categories of metrics shown on the Overview / DC Plan
analytics pages (participation, savings/deferral rate, employer cost,
HCE mix) directly from the raw/staged census file, so a census can be
sanity-checked before a scenario is ever run. Also surfaces data-quality
flags that would otherwise only appear as an import failure.
"""

import csv
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb

from ..models.census_analysis import (
    CensusAnalysisResult,
    CensusDataQualityIssue,
    CensusDeferralRateBucket,
    CensusMetrics,
    CensusSegmentMetrics,
)
from .band_service import BandService
from .census_as_of import resolve_as_of_date
from .sql_security import (
    CENSUS_BIRTH_DATE_COLUMNS,
    CENSUS_COMPENSATION_COLUMNS,
    CENSUS_DEFERRAL_COLUMNS,
    CENSUS_ELIGIBILITY_DATE_COLUMNS,
    CENSUS_EMPLOYER_CORE_COLUMNS,
    CENSUS_EMPLOYER_MATCH_COLUMNS,
    CENSUS_HIRE_DATE_COLUMNS,
    CENSUS_JOB_LEVEL_COLUMNS,
    CENSUS_TERMINATION_DATE_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
)

logger = logging.getLogger(__name__)

IRS_LIMITS_SEED = (
    Path(__file__).parent.parent.parent / "dbt" / "seeds" / "config_irs_limits.csv"
)

_DEPARTMENT_COLUMNS = frozenset({"department"})

# Mirrors AnalyticsService._get_deferral_distribution's bucket scheme so the
# census-side histogram reads the same way as the post-simulation DC Plan one.
_DEFERRAL_BUCKET_ORDER = (
    "0%",
    "1%",
    "2%",
    "3%",
    "4%",
    "5%",
    "6%",
    "7%",
    "8%",
    "9%",
    "10%+",
)
_DEFERRAL_BUCKET_SQL = """
    CASE
      WHEN _deferral_rate IS NULL OR _deferral_rate = 0 THEN '0%'
      WHEN _deferral_rate < 0.015 THEN '1%'
      WHEN _deferral_rate < 0.025 THEN '2%'
      WHEN _deferral_rate < 0.035 THEN '3%'
      WHEN _deferral_rate < 0.045 THEN '4%'
      WHEN _deferral_rate < 0.055 THEN '5%'
      WHEN _deferral_rate < 0.065 THEN '6%'
      WHEN _deferral_rate < 0.075 THEN '7%'
      WHEN _deferral_rate < 0.085 THEN '8%'
      WHEN _deferral_rate < 0.095 THEN '9%'
      ELSE '10%+'
    END
"""


class CensusAnalysisService:
    """Analyzes a raw census file the same way Overview/DC Plan read simulation output."""

    def __init__(
        self, workspaces_root: Path, dbt_seeds_dir: Optional[Path] = None
    ) -> None:
        self.workspaces_root = workspaces_root
        self.band_service = BandService(workspaces_root, dbt_seeds_dir)

    def analyze(
        self,
        workspace_id: str,
        file_path: str,
        as_of_date: Optional[date] = None,
    ) -> CensusAnalysisResult:
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

            id_col = "employee_id" if "employee_id" in columns else None
            birth_col = self._optional_column(columns, CENSUS_BIRTH_DATE_COLUMNS)
            hire_col = self._optional_column(columns, CENSUS_HIRE_DATE_COLUMNS)
            term_col = self._optional_column(columns, CENSUS_TERMINATION_DATE_COLUMNS)
            comp_col = self._optional_column(columns, CENSUS_COMPENSATION_COLUMNS)
            deferral_col = self._optional_column(columns, CENSUS_DEFERRAL_COLUMNS)
            match_col = self._optional_column(columns, CENSUS_EMPLOYER_MATCH_COLUMNS)
            core_col = self._optional_column(columns, CENSUS_EMPLOYER_CORE_COLUMNS)
            eligibility_col = self._optional_column(
                columns, CENSUS_ELIGIBILITY_DATE_COLUMNS
            )
            department_col = self._optional_column(columns, _DEPARTMENT_COLUMNS)
            job_level_col = self._optional_column(columns, CENSUS_JOB_LEVEL_COLUMNS)

            resolved_as_of = resolve_as_of_date(conn, hire_col, term_col, as_of_date)
            active_filter = self._active_filter(columns)

            total_employees = self._scalar(conn, "SELECT COUNT(*) FROM census")
            active_employees = self._scalar(
                conn, f"SELECT COUNT(*) FROM census WHERE {active_filter}"
            )

            hce_threshold = self._hce_threshold_for_year(resolved_as_of.date.year)

            self._build_analyzed_table(
                conn,
                active_filter=active_filter,
                as_of=resolved_as_of.date,
                birth_col=birth_col,
                hire_col=hire_col,
                comp_col=comp_col,
                deferral_col=deferral_col,
                match_col=match_col,
                core_col=core_col,
                eligibility_col=eligibility_col,
                department_col=department_col,
                job_level_col=job_level_col,
                hce_threshold=hce_threshold,
            )

            overall = self._metrics_for_filter(conn, "1=1")

            segments: list[CensusSegmentMetrics] = []
            available_dimensions: list[str] = []

            if department_col:
                segments.extend(
                    self._segment_by_column(conn, "department", "_department")
                )
                available_dimensions.append("department")
            if job_level_col:
                segments.extend(
                    self._segment_by_column(conn, "job_level", "_job_level")
                )
                available_dimensions.append("job_level")
            if birth_col:
                segments.extend(
                    self._segment_by_bands(conn, "age_band", "_age", self._age_bands())
                )
                available_dimensions.append("age_band")
            if hire_col:
                segments.extend(
                    self._segment_by_bands(
                        conn, "tenure_band", "_tenure", self._tenure_bands()
                    )
                )
                available_dimensions.append("tenure_band")
            if hce_threshold is not None and comp_col:
                segments.extend(
                    self._segment_by_column(conn, "hce_status", "_hce_label")
                )
                available_dimensions.append("hce_status")

            data_quality_issues = self._data_quality_issues(
                conn,
                columns=columns,
                id_col=id_col,
                birth_col=birth_col,
                hire_col=hire_col,
                comp_col=comp_col,
                deferral_col=deferral_col,
            )

            deferral_distribution = (
                self._deferral_distribution(conn) if deferral_col else []
            )

            return CensusAnalysisResult(
                total_employees=total_employees,
                active_employees=active_employees,
                overall=overall,
                segments=segments,
                available_segment_dimensions=available_dimensions,
                deferral_rate_distribution=deferral_distribution,
                data_quality_issues=data_quality_issues,
                as_of_date=resolved_as_of.date,
                as_of_date_source=resolved_as_of.source,
                hce_compensation_threshold=hce_threshold,
                source_file=file_path,
                message=self._message(overall, comp_col, deferral_col),
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # File / column resolution
    # ------------------------------------------------------------------

    def _resolve_path(self, workspace_id: str, file_path: str) -> Path:
        resolved = (
            Path(file_path)
            if file_path.startswith("/")
            else self.workspaces_root / workspace_id / file_path
        )
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

    def _optional_column(
        self, existing: set[str], allowed: frozenset[str]
    ) -> Optional[str]:
        preferred = sorted(
            allowed, key=lambda col: (not col.startswith("employee_"), col)
        )
        column = next((col for col in preferred if col in existing), None)
        if column is None:
            return None
        return validate_column_name_from_set(column, set(allowed), "census column")

    def _active_filter(self, columns: set[str]) -> str:
        if "active" not in columns:
            return "1=1"
        return (
            "(active IS NULL "
            "OR UPPER(CAST(active AS VARCHAR)) IN ('ACTIVE', 'Y', '1', 'TRUE', 'YES'))"
        )

    def _age_bands(self):
        try:
            return self.band_service.read_bands_from_csv("age")
        except (FileNotFoundError, ValueError):
            return []

    def _tenure_bands(self):
        try:
            return self.band_service.read_bands_from_csv("tenure")
        except (FileNotFoundError, ValueError):
            return []

    def _hce_threshold_for_year(self, year: int) -> Optional[float]:
        if not IRS_LIMITS_SEED.exists():
            return None
        best: Optional[tuple[int, float]] = None
        try:
            with open(IRS_LIMITS_SEED, "r", newline="") as f:
                for row in csv.DictReader(f):
                    row_year = int(row["limit_year"])
                    threshold = float(row["hce_compensation_threshold"])
                    if row_year <= year and (best is None or row_year > best[0]):
                        best = (row_year, threshold)
        except (KeyError, ValueError, OSError):
            return None
        return best[1] if best else None

    # ------------------------------------------------------------------
    # Analysis table construction
    # ------------------------------------------------------------------

    def _build_analyzed_table(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        active_filter: str,
        as_of: date,
        birth_col: Optional[str],
        hire_col: Optional[str],
        comp_col: Optional[str],
        deferral_col: Optional[str],
        match_col: Optional[str],
        core_col: Optional[str],
        eligibility_col: Optional[str],
        department_col: Optional[str],
        job_level_col: Optional[str],
        hce_threshold: Optional[float],
    ) -> None:
        # Named parameters ($as_of) avoid having to track positional `?` order
        # across a variable number of optional column expressions.
        age_expr = (
            f"FLOOR(DATEDIFF('day', TRY_CAST({birth_col} AS DATE), $as_of::DATE) / 365.25)"
            if birth_col
            else "NULL"
        )
        tenure_expr = (
            f"FLOOR(DATEDIFF('day', TRY_CAST({hire_col} AS DATE), $as_of::DATE) / 365.25)"
            if hire_col
            else "NULL"
        )
        comp_expr = f"TRY_CAST({comp_col} AS DOUBLE)" if comp_col else "NULL"
        deferral_expr = (
            f"TRY_CAST({deferral_col} AS DOUBLE)" if deferral_col else "NULL"
        )
        match_expr = (
            f"COALESCE(TRY_CAST({match_col} AS DOUBLE), 0)" if match_col else "0"
        )
        core_expr = f"COALESCE(TRY_CAST({core_col} AS DOUBLE), 0)" if core_col else "0"
        department_expr = f"{department_col}" if department_col else "NULL"
        job_level_expr = (
            f"CAST({job_level_col} AS VARCHAR)" if job_level_col else "NULL"
        )
        hce_expr = (
            f"CASE WHEN {comp_expr} >= {hce_threshold} THEN 'HCE' ELSE 'NHCE' END"
            if (hce_threshold is not None and comp_col)
            else "NULL"
        )
        eligible_expr = (
            f"(TRY_CAST({eligibility_col} AS DATE) IS NULL "
            f"OR TRY_CAST({eligibility_col} AS DATE) <= $as_of::DATE)"
            if eligibility_col
            else "TRUE"
        )

        conn.execute(
            f"""
            CREATE TABLE analyzed AS
            SELECT
              {age_expr} AS _age,
              {tenure_expr} AS _tenure,
              {comp_expr} AS _compensation,
              {deferral_expr} AS _deferral_rate,
              {match_expr} AS _employer_match,
              {core_expr} AS _employer_core,
              {department_expr} AS _department,
              {job_level_expr} AS _job_level,
              {hce_expr} AS _hce_label,
              ({eligible_expr}) AS _eligible
            FROM census
            WHERE {active_filter}
            """,
            {"as_of": as_of},
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _metrics_for_filter(
        self, conn: duckdb.DuckDBPyConnection, where: str
    ) -> CensusMetrics:
        row = conn.execute(
            f"""
            WITH scoped AS (
              SELECT *,
                CASE WHEN _compensation > 0
                  THEN (_employer_match + _employer_core) / _compensation
                END AS _employer_contribution_rate
              FROM analyzed
              WHERE {where}
            )
            SELECT
              COUNT(*) AS employee_count,
              COUNT(*) FILTER (WHERE _eligible) AS eligible_count,
              COUNT(*) FILTER (WHERE _eligible AND _deferral_rate > 0) AS enrolled_count,
              COUNT(*) FILTER (
                WHERE _eligible AND (_deferral_rate IS NULL OR _deferral_rate = 0)
              ) AS zero_deferral_count,
              AVG(_deferral_rate) FILTER (WHERE _eligible AND _deferral_rate > 0) AS avg_deferral,
              MEDIAN(_deferral_rate) FILTER (WHERE _eligible AND _deferral_rate > 0) AS median_deferral,
              COALESCE(SUM(_compensation) FILTER (WHERE _eligible), 0) AS total_comp,
              COALESCE(SUM(_employer_match) FILTER (WHERE _eligible), 0) AS total_match,
              COALESCE(SUM(_employer_core) FILTER (WHERE _eligible), 0) AS total_core,
              COUNT(*) FILTER (WHERE _hce_label = 'HCE') AS hce_count,
              AVG(_employer_contribution_rate) FILTER (WHERE _eligible) AS avg_employer_rate,
              AVG(COALESCE(_deferral_rate, 0) + _employer_contribution_rate)
                FILTER (WHERE _eligible AND _employer_contribution_rate IS NOT NULL) AS avg_total_savings
            FROM scoped
            """
        ).fetchone()
        assert row is not None

        (
            employee_count,
            eligible_count,
            enrolled_count,
            zero_deferral_count,
            avg_deferral,
            median_deferral,
            total_comp,
            total_match,
            total_core,
            hce_count,
            avg_employer_rate,
            avg_total_savings,
        ) = row

        participation_rate = enrolled_count / eligible_count if eligible_count else None

        return CensusMetrics(
            employee_count=employee_count,
            eligible_count=eligible_count,
            enrolled_count=enrolled_count,
            participation_rate=participation_rate,
            zero_deferral_count=zero_deferral_count,
            average_deferral_rate=avg_deferral,
            median_deferral_rate=median_deferral,
            total_eligible_compensation=float(total_comp),
            total_employer_match=float(total_match),
            total_employer_core=float(total_core),
            total_employer_cost=float(total_match) + float(total_core),
            hce_count=hce_count,
            average_employer_contribution_rate=avg_employer_rate,
            average_total_savings_rate=avg_total_savings,
        )

    def _segment_by_column(
        self, conn: duckdb.DuckDBPyConnection, dimension: str, column: str
    ) -> list[CensusSegmentMetrics]:
        values = [
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT {column} FROM analyzed WHERE {column} IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]
        result = []
        for value in values:
            metrics = self._metrics_for_filter(
                conn, f"{column} = {self._sql_literal(value)}"
            )
            result.append(
                CensusSegmentMetrics(
                    dimension=dimension, value=str(value), **metrics.model_dump()
                )
            )
        return result

    def _segment_by_bands(
        self, conn: duckdb.DuckDBPyConnection, dimension: str, column: str, bands
    ) -> list[CensusSegmentMetrics]:
        result = []
        for band in bands:
            where = f"{column} >= {band.min_value} AND {column} < {band.max_value}"
            metrics = self._metrics_for_filter(conn, where)
            if metrics.employee_count == 0:
                continue
            result.append(
                CensusSegmentMetrics(
                    dimension=dimension, value=band.band_label, **metrics.model_dump()
                )
            )
        return result

    def _sql_literal(self, value: str) -> str:
        # Values here are DISTINCT results pulled back from DuckDB (department names,
        # job level codes, HCE/NHCE labels) -- not user input -- but we still escape
        # quotes defensively before re-interpolating into a WHERE clause.
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def _deferral_distribution(
        self, conn: duckdb.DuckDBPyConnection
    ) -> list[CensusDeferralRateBucket]:
        rows = conn.execute(
            f"""
            SELECT {_DEFERRAL_BUCKET_SQL} AS bucket, COUNT(*) AS cnt
            FROM analyzed
            WHERE _eligible
            GROUP BY 1
            """
        ).fetchall()
        counts = {bucket: count for bucket, count in rows}
        total = sum(counts.values())
        return [
            CensusDeferralRateBucket(
                bucket=bucket,
                count=counts.get(bucket, 0),
                percentage=(
                    round(counts.get(bucket, 0) / total * 100, 2) if total else 0.0
                ),
            )
            for bucket in _DEFERRAL_BUCKET_ORDER
        ]

    # ------------------------------------------------------------------
    # Data quality
    # ------------------------------------------------------------------

    def _data_quality_issues(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        columns: set[str],
        id_col: Optional[str],
        birth_col: Optional[str],
        hire_col: Optional[str],
        comp_col: Optional[str],
        deferral_col: Optional[str],
    ) -> list[CensusDataQualityIssue]:
        issues: list[CensusDataQualityIssue] = []

        required = [
            ("employee_id", id_col, "employee ID"),
            ("employee_birth_date", birth_col, "birth date"),
            ("employee_hire_date", hire_col, "hire date"),
            ("employee_gross_compensation", comp_col, "compensation"),
        ]
        for field_name, col, label in required:
            if col is None:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="missing_required_field",
                        field=field_name,
                        severity="error",
                        count=self._scalar(conn, "SELECT COUNT(*) FROM census"),
                        message=f"No {label} column found in census.",
                    )
                )
                continue
            null_count = self._scalar(
                conn, f"SELECT COUNT(*) FROM census WHERE {col} IS NULL"
            )
            if null_count:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="missing_required_field",
                        field=field_name,
                        severity="error",
                        count=null_count,
                        message=f"{null_count} row(s) missing {label}.",
                    )
                )

        if id_col:
            dupe_count = self._scalar(
                conn,
                f"""
                SELECT COALESCE(SUM(cnt - 1), 0) FROM (
                  SELECT COUNT(*) AS cnt FROM census GROUP BY {id_col} HAVING COUNT(*) > 1
                )
                """,
            )
            if dupe_count:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="duplicate_employee_id",
                        field="employee_id",
                        severity="error",
                        count=dupe_count,
                        message=f"{dupe_count} duplicate employee_id row(s) found.",
                    )
                )

        if birth_col:
            unparseable = self._scalar(
                conn,
                f"SELECT COUNT(*) FROM census WHERE {birth_col} IS NOT NULL AND TRY_CAST({birth_col} AS DATE) IS NULL",
            )
            if unparseable:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="unparseable_date",
                        field="employee_birth_date",
                        severity="warning",
                        count=unparseable,
                        message=f"{unparseable} row(s) have a birth date that could not be parsed.",
                    )
                )

        if hire_col:
            unparseable = self._scalar(
                conn,
                f"SELECT COUNT(*) FROM census WHERE {hire_col} IS NOT NULL AND TRY_CAST({hire_col} AS DATE) IS NULL",
            )
            if unparseable:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="unparseable_date",
                        field="employee_hire_date",
                        severity="warning",
                        count=unparseable,
                        message=f"{unparseable} row(s) have a hire date that could not be parsed.",
                    )
                )

        if comp_col:
            out_of_range = self._scalar(
                conn,
                f"SELECT COUNT(*) FROM census WHERE TRY_CAST({comp_col} AS DOUBLE) IS NOT NULL AND TRY_CAST({comp_col} AS DOUBLE) <= 0",
            )
            if out_of_range:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="out_of_range_value",
                        field="employee_gross_compensation",
                        severity="warning",
                        count=out_of_range,
                        message=f"{out_of_range} row(s) have compensation <= 0.",
                    )
                )

        if deferral_col:
            out_of_range = self._scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM census
                WHERE TRY_CAST({deferral_col} AS DOUBLE) IS NOT NULL
                  AND (TRY_CAST({deferral_col} AS DOUBLE) < 0 OR TRY_CAST({deferral_col} AS DOUBLE) > 1)
                """,
            )
            if out_of_range:
                issues.append(
                    CensusDataQualityIssue(
                        issue_type="out_of_range_value",
                        field="employee_deferral_rate",
                        severity="warning",
                        count=out_of_range,
                        message=(
                            f"{out_of_range} row(s) have a deferral rate outside 0-1 "
                            "(expected a decimal fraction, e.g. 0.06 for 6%)."
                        ),
                    )
                )

        return issues

    def _scalar(self, conn: duckdb.DuckDBPyConnection, sql: str):
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] is not None else 0

    def _message(
        self,
        overall: CensusMetrics,
        comp_col: Optional[str],
        deferral_col: Optional[str],
    ) -> Optional[str]:
        if overall.employee_count == 0:
            return "No active employees found in the census."
        if deferral_col is None:
            return "Census has no deferral rate column; participation and savings-rate metrics are unavailable."
        if comp_col is None:
            return "Census has no compensation column; cost and compensation metrics are unavailable."
        return None
