"""File service for census file uploads and validation."""

import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb

from .sql_security import (
    ALL_CENSUS_COLUMNS,
    CENSUS_BIRTH_DATE_COLUMNS,
    CENSUS_COMPENSATION_COLUMNS,
    CENSUS_HIRE_DATE_COLUMNS,
    CENSUS_JOB_LEVEL_COLUMNS,
    CENSUS_STATUS_COLUMNS,
    CENSUS_TERMINATION_DATE_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
    validate_integer,
)

logger = logging.getLogger(__name__)


class FileService:
    """Service for handling census file uploads and validation."""

    # Required columns for census files
    REQUIRED_COLUMNS = ["employee_id"]

    # Recommended columns (warnings if missing)
    # These match the actual census data schema used by dbt models
    RECOMMENDED_COLUMNS = [
        "employee_id",
        "employee_hire_date",
        "employee_gross_compensation",
        "employee_birth_date",
        "employee_termination_date",
        "active",
    ]

    # Canonical column map: canonical_name -> frozenset of aliases (from sql_security.py)
    _CANONICAL_COLUMN_MAP = {
        "employee_birth_date": CENSUS_BIRTH_DATE_COLUMNS,
        "employee_hire_date": CENSUS_HIRE_DATE_COLUMNS,
        "employee_termination_date": CENSUS_TERMINATION_DATE_COLUMNS,
        "employee_gross_compensation": CENSUS_COMPENSATION_COLUMNS,
        "employee_job_level": CENSUS_JOB_LEVEL_COLUMNS,
        "active": CENSUS_STATUS_COLUMNS,
    }

    # Flattened alias -> canonical map (excludes canonical names themselves)
    COLUMN_ALIASES: Dict[str, str] = {}
    for _canonical, _aliases in _CANONICAL_COLUMN_MAP.items():
        for _alias in _aliases:
            if _alias != _canonical:
                COLUMN_ALIASES[_alias] = _canonical

    # Critical columns — simulation results are unreliable without these
    CRITICAL_COLUMNS = [
        "employee_hire_date",
        "employee_gross_compensation",
        "employee_birth_date",
    ]

    # Field impact descriptions: column → (severity, impact, suggested_action, default_behavior)
    FIELD_IMPACT_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
        "employee_hire_date": {
            "severity": "critical",
            "impact": "Tenure calculations, new hire identification, turnover modeling, and annualized compensation will not work correctly",
            "action": "Add an employee_hire_date column to your census file",
        },
        "employee_gross_compensation": {
            "severity": "critical",
            "impact": "Compensation-based calculations, merit raises, promotion modeling, HCE determination, and contribution calculations will use defaults or produce inaccurate results",
            "action": "Add an employee_gross_compensation column to your census file",
        },
        "employee_birth_date": {
            "severity": "critical",
            "impact": "Age-based calculations, age band segmentation, HCE determination, and retirement eligibility will not work correctly",
            "action": "Add an employee_birth_date column to your census file",
        },
        "employee_termination_date": {
            "severity": "optional",
            "impact": "Terminated employee identification may be incomplete",
            "action": "Add an employee_termination_date column, or ensure the active column is present",
        },
        "active": {
            "severity": "optional",
            "impact": "Employee active/inactive filtering may be unavailable; all employees will be treated as active",
            "action": "Add an active column to your census file",
        },
    }

    # Critical fields for data quality — nulls in these are errors, not warnings
    DATA_QUALITY_CRITICAL_FIELDS = {
        "employee_id",
        "employee_hire_date",
        "employee_gross_compensation",
        "employee_birth_date",
    }

    # All date column sets combined for DQ checks
    ALL_DATE_COLUMN_SETS = (
        CENSUS_BIRTH_DATE_COLUMNS
        | CENSUS_HIRE_DATE_COLUMNS
        | CENSUS_TERMINATION_DATE_COLUMNS
    )

    # Maximum file size: 100MB
    MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".parquet", ".csv"}

    def __init__(self, workspaces_root: Path):
        """Initialize file service with workspace root directory."""
        self.workspaces_root = workspaces_root

    def _get_data_directory(self, workspace_id: str) -> Path:
        """Get the data directory for a workspace."""
        data_dir = self.workspaces_root / workspace_id / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def save_uploaded_file(
        self,
        workspace_id: str,
        file_content: bytes,
        filename: str,
    ) -> Tuple[str, Dict, str]:
        """
        Save an uploaded file, normalizing column names and filename.

        Census files are normalized to canonical column names and saved as
        ``data/census.parquet`` regardless of the original filename.

        Args:
            workspace_id: The workspace ID
            file_content: Raw file bytes
            filename: Original filename

        Returns:
            Tuple of (relative_path, metadata_dict, absolute_path)

        Raises:
            ValueError: If file is invalid or missing required columns
        """
        # Validate extension
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                f"Supported types: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        # Validate size
        if len(file_content) > self.MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File exceeds maximum size of {self.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB"
            )

        # Normalize columns and save as canonical parquet
        data_dir = self._get_data_directory(workspace_id)
        canonical_path, column_renames = self._normalize_and_save_census(
            data_dir, file_content, filename
        )

        try:
            # Parse and validate the normalized file
            metadata = self._parse_and_validate_file(canonical_path)
        except Exception as e:
            # Clean up file if validation fails
            canonical_path.unlink(missing_ok=True)
            raise ValueError(f"Failed to parse file: {e}")

        # Add normalization info to metadata
        metadata["column_renames"] = column_renames
        metadata["original_filename"] = filename

        # Generate auto_mapped structured warnings for each rename
        for rename in column_renames:
            field_info = self.FIELD_IMPACT_DESCRIPTIONS.get(rename["canonical"])
            if field_info:
                metadata["structured_warnings"].append({
                    "field_name": rename["canonical"],
                    "severity": "info",
                    "warning_type": "auto_mapped",
                    "impact_description": field_info["impact"],
                    "detected_alias": rename["original"],
                    "suggested_action": f"Column '{rename['original']}' was auto-renamed to '{rename['canonical']}'",
                })

        # Return canonical path
        relative_path = "data/census.parquet"
        absolute_path = str(canonical_path.resolve())

        return relative_path, metadata, absolute_path

    def _normalize_and_save_census(
        self,
        data_dir: Path,
        file_content: bytes,
        filename: str,
    ) -> Tuple[Path, List[Dict[str, str]]]:
        """
        Normalize column names and save as canonical parquet.

        Writes raw bytes to a temp file, reads into DuckDB, renames alias
        columns to canonical names, and exports as ``data/census.parquet``.

        Args:
            data_dir: Workspace data directory
            file_content: Raw file bytes
            filename: Original filename (used to determine format)

        Returns:
            Tuple of (canonical_path, list_of_renames) where each rename is
            ``{"original": alias, "canonical": canonical_name}``
        """
        suffix = Path(filename).suffix.lower()
        temp_path = data_dir / f"_temp_upload{suffix}"
        canonical_path = data_dir / "census.parquet"

        try:
            # Write raw bytes to temp file
            temp_path.write_bytes(file_content)

            conn = duckdb.connect(":memory:")
            try:
                # Validate temp file path for SQL safety
                try:
                    safe_temp_path = validate_file_path_for_sql(
                        temp_path, [data_dir.parent], context="census upload"
                    )
                except SQLSecurityError as e:
                    raise ValueError(str(e))

                # Read into DuckDB
                if suffix == ".parquet":
                    conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_temp_path}')")
                elif suffix == ".csv":
                    conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_temp_path}', header=true, auto_detect=true)")
                else:
                    raise ValueError(f"Unsupported file type: {suffix}")

                # Get current columns
                columns_result = conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'census'"
                ).fetchall()
                columns = {row[0] for row in columns_result}

                # Detect and rename alias columns
                renames: List[Dict[str, str]] = []
                for alias, canonical in self.COLUMN_ALIASES.items():
                    if alias in columns and canonical not in columns:
                        conn.execute(f'ALTER TABLE census RENAME COLUMN "{alias}" TO "{canonical}"')
                        renames.append({"original": alias, "canonical": canonical})
                        logger.info(f"Auto-renamed column '{alias}' to '{canonical}'")

                # Export as canonical parquet
                try:
                    safe_canonical_path = validate_file_path_for_sql(
                        canonical_path, [data_dir.parent], context="census output"
                    )
                except SQLSecurityError as e:
                    raise ValueError(str(e))

                conn.execute(f"COPY census TO '{safe_canonical_path}' (FORMAT PARQUET)")
                logger.info(f"Saved normalized census to {canonical_path}")

                return canonical_path, renames
            finally:
                conn.close()
        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)

    def _parse_and_validate_file(self, file_path: Path) -> Dict:
        """
        Parse a file and return metadata with validation.

        Args:
            file_path: Path to the file

        Returns:
            Dict with row_count, columns, file_size_bytes, validation_warnings,
            structured_warnings, data_quality_warnings

        Raises:
            ValueError: If required columns are missing
        """
        # Validate file path for SQL safety
        try:
            safe_path = validate_file_path_for_sql(
                file_path, [self.workspaces_root], context="census file"
            )
        except SQLSecurityError as e:
            raise ValueError(str(e))

        suffix = file_path.suffix.lower()
        conn = duckdb.connect(":memory:")

        try:
            if suffix == ".parquet":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')")
            elif suffix == ".csv":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)")
            else:
                raise ValueError(f"Unsupported file type: {suffix}")

            # Get column names
            columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
            columns = [row[0] for row in columns_result]
            warnings: List[str] = []

            # Get row count
            row_count = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]

            # Check required columns
            missing_required = [col for col in self.REQUIRED_COLUMNS if col not in columns]
            if missing_required:
                raise ValueError(
                    f"Missing required column(s): {', '.join(missing_required)}. "
                    f"Found columns: {', '.join(columns)}"
                )

            # Check recommended columns and build structured warnings
            structured_warnings: List[Dict[str, Optional[str]]] = []
            for col in self.RECOMMENDED_COLUMNS:
                if col not in columns:
                    # Check if an alias exists in the file
                    alias_found = None
                    for alias, expected in self.COLUMN_ALIASES.items():
                        if expected == col and alias in columns:
                            alias_found = alias
                            break

                    # Get impact description metadata
                    field_info = self.FIELD_IMPACT_DESCRIPTIONS.get(col)

                    if alias_found:
                        warnings.append(
                            f"Column '{alias_found}' found - consider renaming to '{col}' for consistency"
                        )
                        if field_info:
                            structured_warnings.append({
                                "field_name": col,
                                "severity": field_info["severity"],
                                "warning_type": "alias_found",
                                "impact_description": field_info["impact"],
                                "detected_alias": alias_found,
                                "suggested_action": f"Rename column '{alias_found}' to '{col}' for full compatibility",
                            })
                    else:
                        warnings.append(f"Recommended column missing: {col}")
                        if field_info:
                            structured_warnings.append({
                                "field_name": col,
                                "severity": field_info["severity"],
                                "warning_type": "missing",
                                "impact_description": field_info["impact"],
                                "detected_alias": None,
                                "suggested_action": field_info["action"],
                            })

            # Run row-level data quality checks
            data_quality_warnings = self._run_data_quality_checks(conn, columns, row_count)

            return {
                "row_count": row_count,
                "columns": columns,
                "file_size_bytes": file_path.stat().st_size,
                "validation_warnings": warnings,
                "structured_warnings": structured_warnings,
                "data_quality_warnings": data_quality_warnings,
            }
        except SQLSecurityError:
            raise
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")
        finally:
            conn.close()

    def _run_data_quality_checks(
        self, conn: duckdb.DuckDBPyConnection, columns: List[str], row_count: int
    ) -> List[Dict]:
        """Run row-level data quality checks on the loaded census table."""
        if row_count == 0:
            return []

        warnings: List[Dict] = []

        try:
            warnings.extend(self._check_null_empty(conn, columns, row_count))
            warnings.extend(self._check_date_quality(conn, columns, row_count))
            warnings.extend(self._check_numeric_quality(conn, columns, row_count))
        except Exception as e:
            logger.warning(f"Data quality checks failed (non-fatal): {e}")

        return warnings

    def _check_null_empty(
        self, conn: duckdb.DuckDBPyConnection, columns: List[str], row_count: int
    ) -> List[Dict]:
        """Check for null or empty values in recommended columns."""
        warnings: List[Dict] = []

        for col in self.RECOMMENDED_COLUMNS:
            if col not in columns:
                continue

            try:
                # Get count of affected rows
                count_result = conn.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT CAST("{col}" AS VARCHAR) AS val FROM census
                    ) WHERE val IS NULL OR TRIM(val) = ''
                """).fetchone()

                affected_count = count_result[0]
                if affected_count == 0:
                    continue

                # Get up to 5 sample rows
                sample_rows = conn.execute(f"""
                    SELECT rn, val FROM (
                        SELECT ROW_NUMBER() OVER () AS rn, CAST("{col}" AS VARCHAR) AS val
                        FROM census
                    ) WHERE val IS NULL OR TRIM(val) = ''
                    ORDER BY rn
                    LIMIT 5
                """).fetchall()

                samples = [
                    {"row_number": row[0], "value": row[1]}
                    for row in sample_rows
                ]

                severity = "error" if col in self.DATA_QUALITY_CRITICAL_FIELDS else "warning"
                pct = round((affected_count / row_count) * 100, 1)

                warnings.append({
                    "field_name": col,
                    "check_type": "null_or_empty",
                    "severity": severity,
                    "affected_count": affected_count,
                    "total_count": row_count,
                    "affected_percentage": pct,
                    "message": f"{affected_count} of {row_count} rows ({pct}%) have null or empty {col}",
                    "samples": samples,
                    "suggested_action": f"Review and fill in missing {col} values in your census file",
                })
            except Exception as e:
                logger.debug(f"Null check failed for column {col}: {e}")

        return warnings

    def _check_date_quality(
        self, conn: duckdb.DuckDBPyConnection, columns: List[str], row_count: int
    ) -> List[Dict]:
        """Check for unparseable dates in date columns."""
        warnings: List[Dict] = []

        for col in columns:
            if col not in self.ALL_DATE_COLUMN_SETS:
                continue

            try:
                # Check for values that are non-null strings but fail date parsing
                count_result = conn.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT CAST("{col}" AS VARCHAR) AS val FROM census
                    ) WHERE val IS NOT NULL AND TRIM(val) != ''
                      AND TRY_CAST(val AS DATE) IS NULL
                """).fetchone()

                affected_count = count_result[0]
                if affected_count == 0:
                    continue

                # Get up to 5 samples
                sample_rows = conn.execute(f"""
                    SELECT rn, val FROM (
                        SELECT ROW_NUMBER() OVER () AS rn, CAST("{col}" AS VARCHAR) AS val
                        FROM census
                    ) WHERE val IS NOT NULL AND TRIM(val) != ''
                      AND TRY_CAST(val AS DATE) IS NULL
                    ORDER BY rn
                    LIMIT 5
                """).fetchall()

                samples = [
                    {"row_number": row[0], "value": row[1]}
                    for row in sample_rows
                ]

                pct = round((affected_count / row_count) * 100, 1)

                warnings.append({
                    "field_name": col,
                    "check_type": "unparseable_date",
                    "severity": "error",
                    "affected_count": affected_count,
                    "total_count": row_count,
                    "affected_percentage": pct,
                    "message": f"{affected_count} of {row_count} rows ({pct}%) have unparseable dates in {col}",
                    "samples": samples,
                    "suggested_action": f"Use a consistent date format (YYYY-MM-DD recommended) for {col}",
                })
            except Exception as e:
                logger.debug(f"Date quality check failed for column {col}: {e}")

        return warnings

    def _check_numeric_quality(
        self, conn: duckdb.DuckDBPyConnection, columns: List[str], row_count: int
    ) -> List[Dict]:
        """Check for negative or zero values in compensation columns."""
        warnings: List[Dict] = []

        for col in columns:
            if col not in CENSUS_COMPENSATION_COLUMNS:
                continue

            try:
                count_result = conn.execute(f"""
                    SELECT COUNT(*) FROM (
                        SELECT TRY_CAST("{col}" AS DOUBLE) AS num_val FROM census
                    ) WHERE num_val IS NOT NULL AND num_val <= 0
                """).fetchone()

                affected_count = count_result[0]
                if affected_count == 0:
                    continue

                # Get up to 5 samples
                sample_rows = conn.execute(f"""
                    SELECT rn, val FROM (
                        SELECT ROW_NUMBER() OVER () AS rn,
                               CAST("{col}" AS VARCHAR) AS val,
                               TRY_CAST("{col}" AS DOUBLE) AS num_val
                        FROM census
                    ) WHERE num_val IS NOT NULL AND num_val <= 0
                    ORDER BY rn
                    LIMIT 5
                """).fetchall()

                samples = [
                    {"row_number": row[0], "value": row[1]}
                    for row in sample_rows
                ]

                pct = round((affected_count / row_count) * 100, 1)

                warnings.append({
                    "field_name": col,
                    "check_type": "negative_value",
                    "severity": "warning",
                    "affected_count": affected_count,
                    "total_count": row_count,
                    "affected_percentage": pct,
                    "message": f"{affected_count} of {row_count} rows ({pct}%) have zero or negative {col}",
                    "samples": samples,
                    "suggested_action": f"Verify that {col} values are positive annual compensation amounts",
                })
            except Exception as e:
                logger.debug(f"Numeric quality check failed for column {col}: {e}")

        return warnings

    def validate_path(
        self, workspace_id: str, file_path: str
    ) -> Dict:
        """
        Validate a file path and return metadata.

        Args:
            workspace_id: The workspace ID
            file_path: File path (relative to workspace or absolute)

        Returns:
            Dict with validation result and metadata
        """
        # Resolve path
        if file_path.startswith("/"):
            resolved = Path(file_path)
        else:
            resolved = self.workspaces_root / workspace_id / file_path

        # Check existence
        if not resolved.exists():
            return {
                "valid": False,
                "exists": False,
                "readable": False,
                "error_message": f"File not found: {file_path}",
            }

        # Check it's a file
        if not resolved.is_file():
            return {
                "valid": False,
                "exists": True,
                "readable": False,
                "error_message": f"Path is not a file: {file_path}",
            }

        # Check extension
        suffix = resolved.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            return {
                "valid": False,
                "exists": True,
                "readable": False,
                "error_message": f"Unsupported file type: {suffix}",
            }

        # Try to parse and validate
        try:
            metadata = self._parse_and_validate_file(resolved)
            return {
                "valid": True,
                "exists": True,
                "readable": True,
                "file_size_bytes": metadata["file_size_bytes"],
                "row_count": metadata["row_count"],
                "columns": metadata["columns"],
                "last_modified": datetime.fromtimestamp(resolved.stat().st_mtime),
                "validation_warnings": metadata.get("validation_warnings", []),
                "structured_warnings": metadata.get("structured_warnings", []),
                "data_quality_warnings": metadata.get("data_quality_warnings", []),
            }
        except ValueError as e:
            return {
                "valid": False,
                "exists": True,
                "readable": False,
                "error_message": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error validating file: {e}")
            return {
                "valid": False,
                "exists": True,
                "readable": False,
                "error_message": f"Failed to read file: {e}",
            }

    def list_workspace_files(self, workspace_id: str) -> List[Dict]:
        """
        List all census files in a workspace's data directory.

        Args:
            workspace_id: The workspace ID

        Returns:
            List of file info dicts
        """
        data_dir = self.workspaces_root / workspace_id / "data"
        if not data_dir.exists():
            return []

        files = []
        for file_path in data_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    stat = file_path.stat()
                    files.append({
                        "name": file_path.name,
                        "path": f"data/{file_path.name}",
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime),
                    })
                except Exception as e:
                    logger.warning(f"Failed to stat file {file_path}: {e}")

        return sorted(files, key=lambda f: f["name"])

    def analyze_age_distribution(
        self, workspace_id: str, file_path: str
    ) -> Dict:
        """
        Analyze age distribution from census data, focusing on recent hires.

        Filters to employees hired in the last 12 months to get an accurate
        picture of current hiring patterns rather than overall workforce age.

        Args:
            workspace_id: The workspace ID
            file_path: File path (relative to workspace or absolute)

        Returns:
            Dict with age distribution buckets and weights
        """
        # Resolve path
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
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')")
            elif suffix == ".csv":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)")
            else:
                raise ValueError(f"Unsupported file type: {suffix}")

            # Get column names
            columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
            columns = [row[0] for row in columns_result]

            # Find birth date column (validate against allowlist)
            birth_date_col = None
            for col_name in CENSUS_BIRTH_DATE_COLUMNS:
                if col_name in columns:
                    birth_date_col = validate_column_name_from_set(
                        col_name, CENSUS_BIRTH_DATE_COLUMNS, "birth date column"
                    )
                    break

            if not birth_date_col:
                raise ValueError(
                    "Census file must contain a birth date column "
                    "(employee_birth_date, birth_date, birthdate, or dob)"
                )

            # Find hire date column (validate against allowlist)
            hire_date_col = None
            for col_name in CENSUS_HIRE_DATE_COLUMNS:
                if col_name in columns:
                    hire_date_col = validate_column_name_from_set(
                        col_name, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
                    )
                    break

            # Calculate dates
            today = datetime.now().date()
            today_str = today.isoformat()

            # Filter to active employees if status column exists
            if "active" in columns:
                conn.execute("DELETE FROM census WHERE active != true")
            elif "status" in columns:
                conn.execute("DELETE FROM census WHERE LOWER(status) != 'active'")

            # Check if we should filter to recent hires
            recent_hires_only = False
            recent_year = None

            if hire_date_col:
                # Find the most recent calendar year with hires
                max_hire_date_result = conn.execute(
                    f"SELECT MAX(CAST({hire_date_col} AS DATE)) FROM census"
                ).fetchone()
                max_hire_date = max_hire_date_result[0] if max_hire_date_result else None

                if max_hire_date:
                    recent_year = validate_integer(max_hire_date.year, min_val=1900, max_val=2100, context="year")
                    # Check if we have enough recent hires using parameterized query
                    recent_count = conn.execute(
                        f"SELECT COUNT(*) FROM census WHERE YEAR(CAST({hire_date_col} AS DATE)) = ?",
                        [recent_year]
                    ).fetchone()[0]

                    if recent_count >= 10:
                        conn.execute(
                            f"DELETE FROM census WHERE YEAR(CAST({hire_date_col} AS DATE)) != ?",
                            [recent_year]
                        )
                        recent_hires_only = True

            # Calculate ages using validated column names
            conn.execute("ALTER TABLE census ADD COLUMN _age INTEGER")
            if recent_hires_only and hire_date_col:
                # Age at time of hire
                conn.execute(f"""
                    UPDATE census SET _age = FLOOR(
                        DATEDIFF('day', CAST({birth_date_col} AS DATE), CAST({hire_date_col} AS DATE)) / 365.25
                    )
                """)
            else:
                # Current age using parameterized date
                conn.execute(
                    f"""
                    UPDATE census SET _age = FLOOR(
                        DATEDIFF('day', CAST({birth_date_col} AS DATE), ?::DATE) / 365.25
                    )
                    """,
                    [today_str]
                )

            # Define age buckets matching our seed structure
            age_buckets = [
                (22, 0, 24, "Recent college graduates"),
                (25, 24, 27, "Early career"),
                (28, 27, 30, "Established early career"),
                (32, 30, 34, "Mid-career switchers"),
                (35, 34, 38, "Experienced hires"),
                (40, 38, 43, "Senior experienced"),
                (45, 43, 48, "Mature professionals"),
                (50, 48, 100, "Late career changes"),
            ]

            total_count = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]
            if total_count == 0:
                raise ValueError(
                    "No employees found. "
                    + ("No hires in the last 12 months." if hire_date_col else "")
                )

            distribution = []
            for target_age, min_age, max_age, description in age_buckets:
                # Use parameterized query for age range
                count = conn.execute(
                    "SELECT COUNT(*) FROM census WHERE _age >= ? AND _age < ?",
                    [min_age, max_age]
                ).fetchone()[0]
                weight = round(count / total_count, 4) if total_count > 0 else 0

                distribution.append({
                    "age": target_age,
                    "weight": weight,
                    "description": description,
                    "count": count,
                })

            # Normalize weights to sum to 1.0
            total_weight = sum(d["weight"] for d in distribution)
            if total_weight > 0:
                for d in distribution:
                    d["weight"] = round(d["weight"] / total_weight, 4)

            return {
                "total_employees": total_count,
                "recent_hires_only": recent_hires_only,
                "analysis_type": f"New hires from {recent_year}" if recent_hires_only else "All employees (no recent hire data)",
                "distribution": distribution,
                "source_file": str(file_path),
            }
        finally:
            conn.close()

    def analyze_compensation_by_level(
        self, workspace_id: str, file_path: str, lookback_years: int = 4
    ) -> Dict:
        """
        Analyze compensation ranges from census data.

        If job level column exists, calculates stats by level.
        Otherwise, provides overall compensation distribution with percentile bands
        that can inform job level boundaries.

        For new hire compensation targeting, focuses on recent hires (within lookback_years)
        to get more relevant market-rate data.

        Args:
            workspace_id: The workspace ID
            file_path: File path (relative to workspace or absolute)
            lookback_years: Number of years to look back for recent hires (default 4)

        Returns:
            Dict with compensation statistics (by level if available)
        """
        # Validate lookback_years
        lookback_years = validate_integer(lookback_years, min_val=0, max_val=50, context="lookback_years")

        # Resolve path
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
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')")
            elif suffix == ".csv":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)")
            else:
                raise ValueError(f"Unsupported file type: {suffix}")

            # Get column names
            columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
            columns = [row[0] for row in columns_result]

            # Find compensation column (validate against allowlist)
            comp_col = None
            for col_name in CENSUS_COMPENSATION_COLUMNS:
                if col_name in columns:
                    comp_col = validate_column_name_from_set(
                        col_name, CENSUS_COMPENSATION_COLUMNS, "compensation column"
                    )
                    break

            if not comp_col:
                raise ValueError(
                    "Census file must contain a compensation column "
                    "(employee_gross_compensation, annual_salary, compensation, salary, or base_salary)"
                )

            # Find level column (optional - validate against allowlist)
            level_col = None
            for col_name in CENSUS_JOB_LEVEL_COLUMNS:
                if col_name in columns:
                    level_col = validate_column_name_from_set(
                        col_name, CENSUS_JOB_LEVEL_COLUMNS, "job level column"
                    )
                    break

            # Find hire date column for recent hires analysis (validate against allowlist)
            hire_date_col = None
            for col_name in CENSUS_HIRE_DATE_COLUMNS:
                if col_name in columns:
                    hire_date_col = validate_column_name_from_set(
                        col_name, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
                    )
                    break

            # Add working columns for compensation using validated column names
            conn.execute("ALTER TABLE census ADD COLUMN _compensation DOUBLE")
            conn.execute(f"UPDATE census SET _compensation = CAST({comp_col} AS DOUBLE)")
            if level_col:
                conn.execute("ALTER TABLE census ADD COLUMN _level INTEGER")
                conn.execute(f"UPDATE census SET _level = CAST({level_col} AS INTEGER)")

            # Filter to active employees if status column exists
            if "active" in columns:
                conn.execute("DELETE FROM census WHERE active != true")
            elif "status" in columns:
                conn.execute("DELETE FROM census WHERE LOWER(status) != 'active'")

            # Try to parse hire dates and annualize compensation
            recent_hires_only = False
            lookback_description = None
            annualized = False

            if hire_date_col:
                try:
                    conn.execute("ALTER TABLE census ADD COLUMN _hire_date DATE")
                    conn.execute(f"UPDATE census SET _hire_date = CAST({hire_date_col} AS DATE)")

                    # Find the "census date" - assume it's the max hire date or end of that year
                    max_hire_date_result = conn.execute("SELECT MAX(_hire_date) FROM census").fetchone()
                    max_hire_date = max_hire_date_result[0] if max_hire_date_result else None

                    if max_hire_date:
                        # Assume census is from end of the year of the most recent hire
                        census_year = validate_integer(max_hire_date.year, min_val=1900, max_val=2100, context="year")
                        census_date = date(census_year, 12, 31)
                        census_date_str = census_date.isoformat()

                        # Calculate days worked and annualize compensation using parameterized queries
                        conn.execute("ALTER TABLE census ADD COLUMN _days_worked INTEGER")
                        conn.execute(
                            """
                            UPDATE census SET _days_worked = CASE
                                WHEN YEAR(_hire_date) = ?
                                THEN LEAST(365, GREATEST(1, DATEDIFF('day', _hire_date, ?::DATE)))
                                ELSE 365
                            END
                            """,
                            [census_year, census_date_str]
                        )

                        conn.execute("""
                            UPDATE census SET _compensation = CASE
                                WHEN _days_worked < 365 THEN _compensation * 365.0 / _days_worked
                                ELSE _compensation
                            END
                        """)
                        annualized = True

                        # Now filter to recent hires if requested
                        if lookback_years > 0:
                            cutoff_date = max_hire_date - timedelta(days=lookback_years * 365)
                            cutoff_date_str = cutoff_date.isoformat()
                            recent_count = conn.execute(
                                "SELECT COUNT(*) FROM census WHERE _hire_date >= ?",
                                [cutoff_date_str]
                            ).fetchone()[0]

                            # Need enough data for meaningful analysis (at least 20 employees)
                            if recent_count >= 20:
                                conn.execute(
                                    "DELETE FROM census WHERE _hire_date < ?",
                                    [cutoff_date_str]
                                )
                                recent_hires_only = True
                                lookback_description = f"Hires from last {lookback_years} years ({recent_count} employees, annualized)"
                            else:
                                lookback_description = f"All employees (only {recent_count} recent hires found, need 20+)"
                except SQLSecurityError:
                    raise
                except Exception:
                    # Can't parse dates, skip hire date processing
                    pass

            # Filter out invalid compensation (after annualization)
            conn.execute("DELETE FROM census WHERE _compensation <= 0 OR _compensation >= 2000000")

            total_count = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]
            if total_count == 0:
                raise ValueError("No employees with valid compensation data found")

            # If we have level data, calculate by level
            if level_col:
                level_stats = conn.execute("""
                    SELECT
                        _level,
                        MIN(_compensation) as min_comp,
                        MAX(_compensation) as max_comp,
                        MEDIAN(_compensation) as median_comp,
                        QUANTILE_CONT(_compensation, 0.25) as p25_comp,
                        QUANTILE_CONT(_compensation, 0.75) as p75_comp,
                        AVG(_compensation) as avg_comp,
                        COUNT(*) as employee_count
                    FROM census
                    WHERE _level IS NOT NULL
                    GROUP BY _level
                    ORDER BY _level
                """).fetchall()

                levels = []
                level_names = {1: "Staff", 2: "Manager", 3: "Sr Manager", 4: "Director", 5: "VP"}

                for row in level_stats:
                    level_id = row[0]
                    # Use P25-P75 as the recommended hiring range (more robust than min/max)
                    recommended_min = row[4]  # p25_comp
                    recommended_max = row[5]  # p75_comp
                    levels.append({
                        "level": level_id,
                        "name": level_names.get(level_id, f"Level {level_id}"),
                        "employee_count": row[7],
                        # Raw min/max for reference
                        "raw_min_compensation": round(row[1], 2),
                        "raw_max_compensation": round(row[2], 2),
                        # Recommended range (P25-P75) for new hire targeting
                        "min_compensation": round(recommended_min, 2),
                        "max_compensation": round(recommended_max, 2),
                        "median_compensation": round(row[3], 2),
                        "p25_compensation": round(row[4], 2),
                        "p75_compensation": round(row[5], 2),
                        "avg_compensation": round(row[6], 2),
                    })

                analysis_desc = lookback_description or "All employees"
                if annualized and "annualized" not in analysis_desc.lower():
                    analysis_desc += " (compensation annualized for partial-year employees)"

                return {
                    "total_employees": total_count,
                    "recent_hires_only": recent_hires_only,
                    "lookback_years": lookback_years if recent_hires_only else None,
                    "has_level_data": True,
                    "analysis_type": analysis_desc,
                    "compensation_annualized": annualized,
                    "levels": levels,
                    "source_file": str(file_path),
                }
            else:
                # No level data - provide overall distribution with suggested bands
                overall_stats = conn.execute("""
                    SELECT
                        MIN(_compensation) as min_comp,
                        MAX(_compensation) as max_comp,
                        MEDIAN(_compensation) as median_comp,
                        QUANTILE_CONT(_compensation, 0.05) as p5_comp,
                        QUANTILE_CONT(_compensation, 0.10) as p10_comp,
                        QUANTILE_CONT(_compensation, 0.25) as p25_comp,
                        QUANTILE_CONT(_compensation, 0.50) as p50_comp,
                        QUANTILE_CONT(_compensation, 0.75) as p75_comp,
                        QUANTILE_CONT(_compensation, 0.90) as p90_comp,
                        QUANTILE_CONT(_compensation, 0.95) as p95_comp,
                        QUANTILE_CONT(_compensation, 0.97) as p97_comp,
                        AVG(_compensation) as avg_comp
                    FROM census
                """).fetchone()

                # Create suggested level ranges based on percentiles
                suggested_levels = [
                    {
                        "level": 1,
                        "name": "Staff",
                        "suggested_min": round(overall_stats[3], 0),  # p5
                        "suggested_max": round(overall_stats[5], 0),  # p25
                        "percentile_range": "5th-25th",
                    },
                    {
                        "level": 2,
                        "name": "Manager",
                        "suggested_min": round(overall_stats[5], 0),  # p25
                        "suggested_max": round(overall_stats[6], 0),  # p50
                        "percentile_range": "25th-50th",
                    },
                    {
                        "level": 3,
                        "name": "Sr Manager",
                        "suggested_min": round(overall_stats[6], 0),  # p50
                        "suggested_max": round(overall_stats[7], 0),  # p75
                        "percentile_range": "50th-75th",
                    },
                    {
                        "level": 4,
                        "name": "Director",
                        "suggested_min": round(overall_stats[7], 0),  # p75
                        "suggested_max": round(overall_stats[8], 0),  # p90
                        "percentile_range": "75th-90th",
                    },
                    {
                        "level": 5,
                        "name": "VP",
                        "suggested_min": round(overall_stats[8], 0),  # p90
                        "suggested_max": round(overall_stats[10], 0),  # p97
                        "percentile_range": "90th-97th",
                    },
                ]

                analysis_desc = lookback_description or "All employees"
                if annualized and "annualized" not in analysis_desc.lower():
                    analysis_desc += " (compensation annualized for partial-year employees)"

                return {
                    "total_employees": total_count,
                    "recent_hires_only": recent_hires_only,
                    "lookback_years": lookback_years if recent_hires_only else None,
                    "has_level_data": False,
                    "analysis_type": analysis_desc,
                    "compensation_annualized": annualized,
                    "message": "Census does not have job level data. Showing overall compensation distribution with suggested level ranges based on percentiles of recent hires." if recent_hires_only else "Census does not have job level data. Showing overall compensation distribution with suggested level ranges based on percentiles.",
                    "overall_stats": {
                        "min_compensation": round(overall_stats[0], 2),
                        "max_compensation": round(overall_stats[1], 2),
                        "median_compensation": round(overall_stats[2], 2),
                        "p10_compensation": round(overall_stats[4], 2),
                        "p25_compensation": round(overall_stats[5], 2),
                        "p75_compensation": round(overall_stats[7], 2),
                        "p90_compensation": round(overall_stats[8], 2),
                        "avg_compensation": round(overall_stats[11], 2),
                    },
                    "suggested_levels": suggested_levels,
                    "source_file": str(file_path),
                }
        finally:
            conn.close()
