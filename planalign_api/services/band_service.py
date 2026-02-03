"""Band configuration service for managing age and tenure bands.

This service handles reading, validating, and writing band configurations
to dbt seed CSV files.
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

import duckdb

from ..models.bands import (
    Band,
    BandAnalysisResult,
    BandConfig,
    BandValidationError,
    DistributionStats,
)
from .sql_security import (
    CENSUS_BIRTH_DATE_COLUMNS,
    CENSUS_HIRE_DATE_COLUMNS,
    CENSUS_STATUS_COLUMNS,
    SQLSecurityError,
    validate_column_name_from_set,
    validate_file_path_for_sql,
    validate_integer,
    validate_numeric,
)

logger = logging.getLogger(__name__)

# Path to dbt seeds directory (relative to project root)
DBT_SEEDS_DIR = Path(__file__).parent.parent.parent / "dbt" / "seeds"


class BandService:
    """Service for band configuration management."""

    def __init__(self, workspaces_root: Path, dbt_seeds_dir: Optional[Path] = None):
        """
        Initialize band service.

        Args:
            workspaces_root: Root directory for workspaces (used for census analysis)
            dbt_seeds_dir: Override path to dbt seeds directory (for testing)
        """
        self.workspaces_root = workspaces_root
        self.dbt_seeds_dir = dbt_seeds_dir or DBT_SEEDS_DIR

    def _get_band_csv_path(self, band_type: str) -> Path:
        """Get the path to a band configuration CSV file."""
        filename = f"config_{band_type}_bands.csv"
        return self.dbt_seeds_dir / filename

    # -------------------------------------------------------------------------
    # CSV Read/Write Utilities (T005)
    # -------------------------------------------------------------------------

    def read_bands_from_csv(self, band_type: str) -> List[Band]:
        """
        Read band definitions from a CSV file.

        Args:
            band_type: Type of bands ("age" or "tenure")

        Returns:
            List of Band objects

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV data is malformed
        """
        csv_path = self._get_band_csv_path(band_type)

        if not csv_path.exists():
            raise FileNotFoundError(f"Band configuration file not found: {csv_path}")

        bands = []
        try:
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bands.append(
                        Band(
                            band_id=int(row["band_id"]),
                            band_label=row["band_label"],
                            min_value=int(row["min_value"]),
                            max_value=int(row["max_value"]),
                            display_order=int(row["display_order"]),
                        )
                    )
        except KeyError as e:
            raise ValueError(f"Missing required column in CSV: {e}")
        except ValueError as e:
            raise ValueError(f"Invalid data in CSV: {e}")

        # Sort by display_order for consistency
        bands.sort(key=lambda b: b.display_order)
        return bands

    def write_bands_to_csv(self, band_type: str, bands: List[Band]) -> None:
        """
        Write band definitions to a CSV file.

        Args:
            band_type: Type of bands ("age" or "tenure")
            bands: List of Band objects to write

        Raises:
            IOError: If unable to write to file
        """
        csv_path = self._get_band_csv_path(band_type)

        # Sort by display_order before writing
        sorted_bands = sorted(bands, key=lambda b: b.display_order)

        try:
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["band_id", "band_label", "min_value", "max_value", "display_order"],
                )
                writer.writeheader()
                for band in sorted_bands:
                    writer.writerow(
                        {
                            "band_id": band.band_id,
                            "band_label": band.band_label,
                            "min_value": band.min_value,
                            "max_value": band.max_value,
                            "display_order": band.display_order,
                        }
                    )
            logger.info(f"Successfully wrote {len(bands)} bands to {csv_path}")
        except IOError as e:
            logger.error(f"Failed to write bands to {csv_path}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Band Validation Logic (T004)
    # -------------------------------------------------------------------------

    def validate_bands(self, bands: List[Band], band_type: str) -> List[BandValidationError]:
        """
        Validate a list of bands for gaps, overlaps, and coverage.

        Validation rules:
        - Bands use [min, max) interval convention
        - No gaps between consecutive bands (sorted by display_order)
        - No overlapping ranges
        - First band must start at 0
        - Each band's max_value must be > min_value

        Args:
            bands: List of bands to validate
            band_type: "age" or "tenure" (for error messages)

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[BandValidationError] = []

        if not bands:
            errors.append(
                BandValidationError(
                    band_type=band_type,
                    error_type="coverage",
                    message="At least one band is required",
                    band_ids=[],
                )
            )
            return errors

        # Sort bands by min_value for validation
        sorted_bands = sorted(bands, key=lambda b: b.min_value)

        # Check first band starts at 0
        if sorted_bands[0].min_value != 0:
            errors.append(
                BandValidationError(
                    band_type=band_type,
                    error_type="coverage",
                    message=f"First band must start at 0, but starts at {sorted_bands[0].min_value}",
                    band_ids=[sorted_bands[0].band_id],
                )
            )

        # Check each band's range is valid
        for band in sorted_bands:
            if band.max_value <= band.min_value:
                errors.append(
                    BandValidationError(
                        band_type=band_type,
                        error_type="invalid_range",
                        message=f"Band '{band.band_label}' has invalid range: max_value ({band.max_value}) must be greater than min_value ({band.min_value})",
                        band_ids=[band.band_id],
                    )
                )

        # Check for gaps and overlaps between consecutive bands
        for i in range(len(sorted_bands) - 1):
            current = sorted_bands[i]
            next_band = sorted_bands[i + 1]

            # Check for gap: current.max_value should equal next.min_value
            if current.max_value < next_band.min_value:
                errors.append(
                    BandValidationError(
                        band_type=band_type,
                        error_type="gap",
                        message=f"Gap detected between bands: {current.max_value} to {next_band.min_value}",
                        band_ids=[current.band_id, next_band.band_id],
                    )
                )

            # Check for overlap: current.max_value should not exceed next.min_value
            if current.max_value > next_band.min_value:
                errors.append(
                    BandValidationError(
                        band_type=band_type,
                        error_type="overlap",
                        message=f"Overlap detected between bands at value {next_band.min_value}",
                        band_ids=[current.band_id, next_band.band_id],
                    )
                )

        return errors

    # -------------------------------------------------------------------------
    # Read Band Configurations (T010)
    # -------------------------------------------------------------------------

    def read_band_configs(self) -> BandConfig:
        """
        Read all band configurations from CSV files.

        Returns:
            BandConfig with age_bands and tenure_bands

        Raises:
            FileNotFoundError: If any CSV file is missing
        """
        age_bands = self.read_bands_from_csv("age")
        tenure_bands = self.read_bands_from_csv("tenure")

        return BandConfig(age_bands=age_bands, tenure_bands=tenure_bands)

    # -------------------------------------------------------------------------
    # Save Band Configurations (T017)
    # -------------------------------------------------------------------------

    def save_band_configs(
        self, age_bands: List[Band], tenure_bands: List[Band]
    ) -> Tuple[bool, List[BandValidationError], str]:
        """
        Validate and save band configurations.

        Args:
            age_bands: New age band definitions
            tenure_bands: New tenure band definitions

        Returns:
            Tuple of (success, validation_errors, message)
        """
        # Validate both band types
        all_errors: List[BandValidationError] = []
        all_errors.extend(self.validate_bands(age_bands, "age"))
        all_errors.extend(self.validate_bands(tenure_bands, "tenure"))

        if all_errors:
            return (False, all_errors, "Validation failed - see errors for details")

        # Write to CSV files
        try:
            self.write_bands_to_csv("age", age_bands)
            self.write_bands_to_csv("tenure", tenure_bands)
            return (True, [], "Band configurations saved successfully")
        except IOError as e:
            return (False, [], f"Failed to save band configurations: {e}")

    # -------------------------------------------------------------------------
    # Census Analysis for Age Bands (T027-T028)
    # -------------------------------------------------------------------------

    def analyze_age_distribution_for_bands(
        self, workspace_id: str, file_path: str, num_bands: int = 6
    ) -> BandAnalysisResult:
        """
        Analyze census data and suggest optimal age band boundaries.

        Uses percentile-based boundary detection to create bands that
        follow the data distribution.

        Args:
            workspace_id: Workspace ID
            file_path: Path to census file (relative to workspace or absolute)
            num_bands: Number of bands to suggest (default 6)

        Returns:
            BandAnalysisResult with suggested bands and statistics
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
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')")
            elif suffix == ".csv":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)")
            else:
                conn.close()
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
                conn.close()
                raise ValueError(
                    "Census file must contain a birth date column "
                    "(employee_birth_date, birth_date, birthdate, or dob)"
                )

            # Find hire date column for recent hires analysis (validate against allowlist)
            hire_date_col = None
            for col_name in CENSUS_HIRE_DATE_COLUMNS:
                if col_name in columns:
                    hire_date_col = validate_column_name_from_set(
                        col_name, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
                    )
                    break

            # Calculate dates
            today = date.today()
            today_str = today.isoformat()

            # Filter to active employees (using validated column names)
            if "active" in columns:
                conn.execute("DELETE FROM census WHERE active != true")
            elif "status" in columns:
                conn.execute("DELETE FROM census WHERE LOWER(status) != 'active'")

            # Check for recent hires
            recent_hires_only = False
            recent_year = None

            if hire_date_col:
                try:
                    # Use validated column name - safe for interpolation
                    max_hire_date_result = conn.execute(
                        f"SELECT MAX(CAST({hire_date_col} AS DATE)) FROM census"
                    ).fetchone()
                    max_hire_date = max_hire_date_result[0] if max_hire_date_result else None

                    if max_hire_date:
                        recent_year = validate_integer(max_hire_date.year, min_val=1900, max_val=2100, context="year")
                        # Use parameterized query for the year value
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
                except SQLSecurityError:
                    raise
                except Exception:
                    hire_date_col = None  # Could not parse, skip

            # Calculate age using validated column names
            conn.execute("ALTER TABLE census ADD COLUMN _age INTEGER")
            if recent_hires_only and hire_date_col:
                conn.execute(f"""
                    UPDATE census SET _age = FLOOR(
                        DATEDIFF('day', CAST({birth_date_col} AS DATE), CAST({hire_date_col} AS DATE)) / 365.25
                    )
                """)
            else:
                conn.execute(
                    f"""
                    UPDATE census SET _age = FLOOR(
                        DATEDIFF('day', CAST({birth_date_col} AS DATE), ?::DATE) / 365.25
                    )
                    """,
                    [today_str]
                )

            # Filter out invalid ages
            conn.execute("DELETE FROM census WHERE _age < 18 OR _age >= 100")

            total_count = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]
            if total_count == 0:
                conn.close()
                raise ValueError("No employees with valid age data found")

            # Calculate distribution statistics
            stats = conn.execute("""
                SELECT
                    COUNT(_age) as total,
                    MIN(_age) as min_age,
                    MAX(_age) as max_age,
                    MEDIAN(_age) as median_age,
                    AVG(_age) as mean_age,
                    QUANTILE_CONT(_age, 0.10) as p10,
                    QUANTILE_CONT(_age, 0.25) as p25,
                    QUANTILE_CONT(_age, 0.50) as p50,
                    QUANTILE_CONT(_age, 0.75) as p75,
                    QUANTILE_CONT(_age, 0.90) as p90
                FROM census
            """).fetchone()

            # Generate suggested bands using percentile-based boundaries
            suggested_bands = self._generate_age_bands_from_percentiles_duckdb(
                conn=conn,
                num_bands=num_bands,
            )

            analysis_type = f"Recent hires from {recent_year}" if recent_hires_only else "All employees"

            return BandAnalysisResult(
                suggested_bands=suggested_bands,
                distribution_stats=DistributionStats(
                    total_employees=int(stats[0]),
                    min_value=int(stats[1]),
                    max_value=int(stats[2]),
                    median_value=float(stats[3]),
                    mean_value=float(stats[4]),
                    percentiles={
                        10: float(stats[5]),
                        25: float(stats[6]),
                        50: float(stats[7]),
                        75: float(stats[8]),
                        90: float(stats[9]),
                    },
                ),
                analysis_type=analysis_type,
                source_file=str(file_path),
            )
        finally:
            conn.close()

    def _generate_age_bands_from_percentiles_duckdb(self, conn: duckdb.DuckDBPyConnection, num_bands: int) -> List[Band]:
        """Generate age bands based on data percentiles using DuckDB."""
        # Validate num_bands
        num_bands = validate_integer(num_bands, min_val=2, max_val=20, context="num_bands")

        # Define percentile boundaries for different band counts
        if num_bands == 6:
            percentiles = [0, 10, 25, 50, 75, 90, 100]
        elif num_bands == 5:
            percentiles = [0, 20, 40, 60, 80, 100]
        else:
            # Even distribution for other counts
            percentiles = [int(100 * i / num_bands) for i in range(num_bands + 1)]

        # Get age values at each percentile
        boundaries = []
        for p in percentiles:
            if p == 0:
                boundaries.append(0)  # Always start at 0
            elif p == 100:
                boundaries.append(999)  # Upper bound
            else:
                # Validate percentile value before use
                p_decimal = validate_numeric(p / 100, context="percentile")
                val = conn.execute(
                    "SELECT QUANTILE_CONT(_age, ?) FROM census",
                    [p_decimal]
                ).fetchone()[0]
                boundaries.append(int(val))

        # Ensure boundaries are strictly increasing
        for i in range(1, len(boundaries)):
            if boundaries[i] <= boundaries[i - 1]:
                boundaries[i] = boundaries[i - 1] + 1

        # Generate band objects
        bands = []
        for i in range(len(boundaries) - 1):
            min_val = boundaries[i]
            max_val = boundaries[i + 1]

            # Generate label
            if min_val == 0:
                label = f"< {max_val}"
            elif max_val == 999:
                label = f"{min_val}+"
            else:
                label = f"{min_val}-{max_val - 1}"

            bands.append(
                Band(
                    band_id=i + 1,
                    band_label=label,
                    min_value=min_val,
                    max_value=max_val,
                    display_order=i + 1,
                )
            )

        return bands

    # -------------------------------------------------------------------------
    # Census Analysis for Tenure Bands (T035)
    # -------------------------------------------------------------------------

    def analyze_tenure_distribution_for_bands(
        self, workspace_id: str, file_path: str, num_bands: int = 5
    ) -> BandAnalysisResult:
        """
        Analyze census data and suggest optimal tenure band boundaries.

        Uses percentile-based boundary detection to create bands that
        follow the data distribution.

        Args:
            workspace_id: Workspace ID
            file_path: Path to census file (relative to workspace or absolute)
            num_bands: Number of bands to suggest (default 5)

        Returns:
            BandAnalysisResult with suggested bands and statistics
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
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_parquet('{safe_path}')")
            elif suffix == ".csv":
                conn.execute(f"CREATE TABLE census AS SELECT * FROM read_csv('{safe_path}', header=true, auto_detect=true)")
            else:
                conn.close()
                raise ValueError(f"Unsupported file type: {suffix}")

            # Get column names
            columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
            columns = [row[0] for row in columns_result]

            # Find hire date column (validate against allowlist)
            hire_date_col = None
            for col_name in CENSUS_HIRE_DATE_COLUMNS:
                if col_name in columns:
                    hire_date_col = validate_column_name_from_set(
                        col_name, CENSUS_HIRE_DATE_COLUMNS, "hire date column"
                    )
                    break

            if not hire_date_col:
                conn.close()
                raise ValueError(
                    "Census file must contain a hire date column "
                    "(employee_hire_date, hire_date, hiredate, or start_date)"
                )

            # Calculate dates
            today = date.today()
            today_str = today.isoformat()

            # Filter to active employees
            if "active" in columns:
                conn.execute("DELETE FROM census WHERE active != true")
            elif "status" in columns:
                conn.execute("DELETE FROM census WHERE LOWER(status) != 'active'")

            # Calculate tenure in years using validated column name and parameterized date
            conn.execute("ALTER TABLE census ADD COLUMN _tenure INTEGER")
            conn.execute(
                f"""
                UPDATE census SET _tenure = FLOOR(
                    DATEDIFF('day', CAST({hire_date_col} AS DATE), ?::DATE) / 365.25
                )
                """,
                [today_str]
            )

            # Filter out invalid tenure (negative or very high)
            conn.execute("DELETE FROM census WHERE _tenure < 0 OR _tenure >= 100")

            total_count = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]
            if total_count == 0:
                conn.close()
                raise ValueError("No employees with valid tenure data found")

            # Calculate distribution statistics
            stats = conn.execute("""
                SELECT
                    COUNT(_tenure) as total,
                    MIN(_tenure) as min_tenure,
                    MAX(_tenure) as max_tenure,
                    MEDIAN(_tenure) as median_tenure,
                    AVG(_tenure) as mean_tenure,
                    QUANTILE_CONT(_tenure, 0.10) as p10,
                    QUANTILE_CONT(_tenure, 0.25) as p25,
                    QUANTILE_CONT(_tenure, 0.50) as p50,
                    QUANTILE_CONT(_tenure, 0.75) as p75,
                    QUANTILE_CONT(_tenure, 0.90) as p90
                FROM census
            """).fetchone()

            # Generate suggested bands using percentile-based boundaries
            suggested_bands = self._generate_tenure_bands_from_percentiles_duckdb(
                conn=conn,
                num_bands=num_bands,
            )

            return BandAnalysisResult(
                suggested_bands=suggested_bands,
                distribution_stats=DistributionStats(
                    total_employees=int(stats[0]),
                    min_value=int(stats[1]),
                    max_value=int(stats[2]),
                    median_value=float(stats[3]),
                    mean_value=float(stats[4]),
                    percentiles={
                        10: float(stats[5]),
                        25: float(stats[6]),
                        50: float(stats[7]),
                        75: float(stats[8]),
                        90: float(stats[9]),
                    },
                ),
                analysis_type="All employees",
                source_file=str(file_path),
            )
        finally:
            conn.close()

    def _generate_tenure_bands_from_percentiles_duckdb(self, conn: duckdb.DuckDBPyConnection, num_bands: int) -> List[Band]:
        """Generate tenure bands based on data percentiles using DuckDB."""
        # Validate num_bands
        num_bands = validate_integer(num_bands, min_val=2, max_val=20, context="num_bands")

        # For tenure, use even percentile distribution
        percentiles = [int(100 * i / num_bands) for i in range(num_bands + 1)]

        # Get tenure values at each percentile
        boundaries = []
        for p in percentiles:
            if p == 0:
                boundaries.append(0)  # Always start at 0
            elif p == 100:
                boundaries.append(999)  # Upper bound
            else:
                # Validate percentile value before use
                p_decimal = validate_numeric(p / 100, context="percentile")
                val = conn.execute(
                    "SELECT QUANTILE_CONT(_tenure, ?) FROM census",
                    [p_decimal]
                ).fetchone()[0]
                boundaries.append(int(val))

        # Ensure boundaries are strictly increasing
        for i in range(1, len(boundaries)):
            if boundaries[i] <= boundaries[i - 1]:
                boundaries[i] = boundaries[i - 1] + 1

        # Generate band objects
        bands = []
        for i in range(len(boundaries) - 1):
            min_val = boundaries[i]
            max_val = boundaries[i + 1]

            # Generate label
            if min_val == 0:
                label = f"< {max_val}"
            elif max_val == 999:
                label = f"{min_val}+"
            else:
                label = f"{min_val}-{max_val - 1}"

            bands.append(
                Band(
                    band_id=i + 1,
                    band_label=label,
                    min_value=min_val,
                    max_value=max_val,
                    display_order=i + 1,
                )
            )

        return bands
