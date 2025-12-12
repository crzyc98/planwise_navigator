"""Band configuration service for managing age and tenure bands.

This service handles reading, validating, and writing band configurations
to dbt seed CSV files.
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

import polars as pl

from ..models.bands import (
    Band,
    BandAnalysisResult,
    BandConfig,
    BandValidationError,
    DistributionStats,
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

        # Read the file
        suffix = resolved.suffix.lower()
        if suffix == ".parquet":
            df = pl.read_parquet(resolved)
        elif suffix == ".csv":
            df = pl.read_csv(resolved, infer_schema_length=10000)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Find birth date column
        birth_date_col = None
        for col_name in ["employee_birth_date", "birth_date", "birthdate", "dob"]:
            if col_name in df.columns:
                birth_date_col = col_name
                break

        if not birth_date_col:
            raise ValueError(
                "Census file must contain a birth date column "
                "(employee_birth_date, birth_date, birthdate, or dob)"
            )

        # Find hire date column for recent hires analysis
        hire_date_col = None
        for col_name in ["employee_hire_date", "hire_date", "hiredate", "start_date"]:
            if col_name in df.columns:
                hire_date_col = col_name
                break

        # Calculate dates
        today = date.today()

        # Parse birth dates
        try:
            df = df.with_columns([pl.col(birth_date_col).cast(pl.Date).alias("_birth_date")])
        except Exception:
            df = df.with_columns([pl.col(birth_date_col).str.to_date().alias("_birth_date")])

        # Parse hire dates if available
        if hire_date_col:
            try:
                df = df.with_columns([pl.col(hire_date_col).cast(pl.Date).alias("_hire_date")])
            except Exception:
                try:
                    df = df.with_columns([pl.col(hire_date_col).str.to_date().alias("_hire_date")])
                except Exception:
                    hire_date_col = None  # Could not parse, skip

        # Filter to active employees
        if "active" in df.columns:
            df = df.filter(pl.col("active") == True)  # noqa: E712
        elif "status" in df.columns:
            df = df.filter(pl.col("status").str.to_lowercase() == "active")

        # Filter to recent hires if hire date is available
        recent_hires_only = False
        recent_year = None
        if hire_date_col and "_hire_date" in df.columns:
            max_hire_date = df.select(pl.col("_hire_date").max()).item()
            if max_hire_date:
                recent_year = max_hire_date.year
                recent_hires = df.filter(pl.col("_hire_date").dt.year() == recent_year)
                if recent_hires.height >= 10:
                    df = recent_hires
                    recent_hires_only = True

        # Calculate age at hire (if recent hires) or current age
        if recent_hires_only and "_hire_date" in df.columns:
            df = df.with_columns(
                [
                    ((pl.col("_hire_date") - pl.col("_birth_date")).dt.total_days() / 365.25)
                    .floor()
                    .cast(pl.Int32)
                    .alias("_age")
                ]
            )
        else:
            df = df.with_columns(
                [
                    ((pl.lit(today) - pl.col("_birth_date")).dt.total_days() / 365.25)
                    .floor()
                    .cast(pl.Int32)
                    .alias("_age")
                ]
            )

        # Filter out invalid ages
        df = df.filter((pl.col("_age") >= 18) & (pl.col("_age") < 100))

        if df.height == 0:
            raise ValueError("No employees with valid age data found")

        # Calculate distribution statistics
        stats = df.select(
            [
                pl.col("_age").count().alias("total"),
                pl.col("_age").min().alias("min_age"),
                pl.col("_age").max().alias("max_age"),
                pl.col("_age").median().alias("median_age"),
                pl.col("_age").mean().alias("mean_age"),
                pl.col("_age").quantile(0.10).alias("p10"),
                pl.col("_age").quantile(0.25).alias("p25"),
                pl.col("_age").quantile(0.50).alias("p50"),
                pl.col("_age").quantile(0.75).alias("p75"),
                pl.col("_age").quantile(0.90).alias("p90"),
            ]
        ).to_dicts()[0]

        # Generate suggested bands using percentile-based boundaries
        # For 6 bands: 0%, 10%, 25%, 50%, 75%, 90%, 100%
        suggested_bands = self._generate_age_bands_from_percentiles(
            df=df,
            num_bands=num_bands,
        )

        analysis_type = f"Recent hires from {recent_year}" if recent_hires_only else "All employees"

        return BandAnalysisResult(
            suggested_bands=suggested_bands,
            distribution_stats=DistributionStats(
                total_employees=int(stats["total"]),
                min_value=int(stats["min_age"]),
                max_value=int(stats["max_age"]),
                median_value=float(stats["median_age"]),
                mean_value=float(stats["mean_age"]),
                percentiles={
                    10: float(stats["p10"]),
                    25: float(stats["p25"]),
                    50: float(stats["p50"]),
                    75: float(stats["p75"]),
                    90: float(stats["p90"]),
                },
            ),
            analysis_type=analysis_type,
            source_file=str(file_path),
        )

    def _generate_age_bands_from_percentiles(self, df: pl.DataFrame, num_bands: int) -> List[Band]:
        """Generate age bands based on data percentiles."""
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
                val = df.select(pl.col("_age").quantile(p / 100)).item()
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

        # Read the file
        suffix = resolved.suffix.lower()
        if suffix == ".parquet":
            df = pl.read_parquet(resolved)
        elif suffix == ".csv":
            df = pl.read_csv(resolved, infer_schema_length=10000)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Find hire date column
        hire_date_col = None
        for col_name in ["employee_hire_date", "hire_date", "hiredate", "start_date"]:
            if col_name in df.columns:
                hire_date_col = col_name
                break

        if not hire_date_col:
            raise ValueError(
                "Census file must contain a hire date column "
                "(employee_hire_date, hire_date, hiredate, or start_date)"
            )

        # Calculate dates
        today = date.today()

        # Parse hire dates
        try:
            df = df.with_columns([pl.col(hire_date_col).cast(pl.Date).alias("_hire_date")])
        except Exception:
            df = df.with_columns([pl.col(hire_date_col).str.to_date().alias("_hire_date")])

        # Filter to active employees
        if "active" in df.columns:
            df = df.filter(pl.col("active") == True)  # noqa: E712
        elif "status" in df.columns:
            df = df.filter(pl.col("status").str.to_lowercase() == "active")

        # Calculate tenure in years
        df = df.with_columns(
            [
                ((pl.lit(today) - pl.col("_hire_date")).dt.total_days() / 365.25)
                .floor()
                .cast(pl.Int32)
                .alias("_tenure")
            ]
        )

        # Filter out invalid tenure (negative or very high)
        df = df.filter((pl.col("_tenure") >= 0) & (pl.col("_tenure") < 100))

        if df.height == 0:
            raise ValueError("No employees with valid tenure data found")

        # Calculate distribution statistics
        stats = df.select(
            [
                pl.col("_tenure").count().alias("total"),
                pl.col("_tenure").min().alias("min_tenure"),
                pl.col("_tenure").max().alias("max_tenure"),
                pl.col("_tenure").median().alias("median_tenure"),
                pl.col("_tenure").mean().alias("mean_tenure"),
                pl.col("_tenure").quantile(0.10).alias("p10"),
                pl.col("_tenure").quantile(0.25).alias("p25"),
                pl.col("_tenure").quantile(0.50).alias("p50"),
                pl.col("_tenure").quantile(0.75).alias("p75"),
                pl.col("_tenure").quantile(0.90).alias("p90"),
            ]
        ).to_dicts()[0]

        # Generate suggested bands using percentile-based boundaries
        suggested_bands = self._generate_tenure_bands_from_percentiles(
            df=df,
            num_bands=num_bands,
        )

        return BandAnalysisResult(
            suggested_bands=suggested_bands,
            distribution_stats=DistributionStats(
                total_employees=int(stats["total"]),
                min_value=int(stats["min_tenure"]),
                max_value=int(stats["max_tenure"]),
                median_value=float(stats["median_tenure"]),
                mean_value=float(stats["mean_tenure"]),
                percentiles={
                    10: float(stats["p10"]),
                    25: float(stats["p25"]),
                    50: float(stats["p50"]),
                    75: float(stats["p75"]),
                    90: float(stats["p90"]),
                },
            ),
            analysis_type="All employees",
            source_file=str(file_path),
        )

    def _generate_tenure_bands_from_percentiles(self, df: pl.DataFrame, num_bands: int) -> List[Band]:
        """Generate tenure bands based on data percentiles."""
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
                val = df.select(pl.col("_tenure").quantile(p / 100)).item()
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
