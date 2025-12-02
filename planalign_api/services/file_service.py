"""File service for census file uploads and validation."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl

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

    # Column aliases - maps common alternative names to expected names
    # Used for informative messages, not auto-renaming
    COLUMN_ALIASES = {
        "hire_date": "employee_hire_date",
        "birth_date": "employee_birth_date",
        "termination_date": "employee_termination_date",
        "annual_salary": "employee_gross_compensation",
        "compensation": "employee_gross_compensation",
        "status": "active",
    }

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
    ) -> Tuple[str, Dict]:
        """
        Save an uploaded file and return its path and metadata.

        Args:
            workspace_id: The workspace ID
            file_content: Raw file bytes
            filename: Original filename

        Returns:
            Tuple of (relative_path, metadata_dict)

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

        # Determine target path
        data_dir = self._get_data_directory(workspace_id)
        file_path = data_dir / filename

        # Write file
        file_path.write_bytes(file_content)
        logger.info(f"Saved uploaded file to {file_path}")

        try:
            # Parse and validate the file
            metadata = self._parse_and_validate_file(file_path)
        except Exception as e:
            # Clean up file if validation fails
            file_path.unlink(missing_ok=True)
            raise ValueError(f"Failed to parse file: {e}")

        # Return relative path for storage in config
        relative_path = f"data/{filename}"

        return relative_path, metadata

    def _parse_and_validate_file(self, file_path: Path) -> Dict:
        """
        Parse a file and return metadata with validation.

        Args:
            file_path: Path to the file

        Returns:
            Dict with row_count, columns, file_size_bytes, validation_warnings

        Raises:
            ValueError: If required columns are missing
        """
        suffix = file_path.suffix.lower()

        try:
            if suffix == ".parquet":
                df = pl.read_parquet(file_path)
            elif suffix == ".csv":
                df = pl.read_csv(file_path, infer_schema_length=10000)
            else:
                raise ValueError(f"Unsupported file type: {suffix}")
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")

        columns = df.columns
        warnings: List[str] = []

        # Check required columns
        missing_required = [col for col in self.REQUIRED_COLUMNS if col not in columns]
        if missing_required:
            raise ValueError(
                f"Missing required column(s): {', '.join(missing_required)}. "
                f"Found columns: {', '.join(columns)}"
            )

        # Check recommended columns
        for col in self.RECOMMENDED_COLUMNS:
            if col not in columns:
                # Check if an alias exists in the file
                alias_found = None
                for alias, expected in self.COLUMN_ALIASES.items():
                    if expected == col and alias in columns:
                        alias_found = alias
                        break

                if alias_found:
                    warnings.append(
                        f"Column '{alias_found}' found - consider renaming to '{col}' for consistency"
                    )
                else:
                    warnings.append(f"Recommended column missing: {col}")

        return {
            "row_count": len(df),
            "columns": columns,
            "file_size_bytes": file_path.stat().st_size,
            "validation_warnings": warnings,
        }

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

        # Find hire date column
        hire_date_col = None
        for col_name in ["employee_hire_date", "hire_date", "hiredate", "start_date"]:
            if col_name in df.columns:
                hire_date_col = col_name
                break

        # Calculate dates
        today = datetime.now().date()

        # Parse birth dates
        try:
            df = df.with_columns([
                pl.col(birth_date_col).cast(pl.Date).alias("_birth_date")
            ])
        except Exception:
            # Try string parsing if direct cast fails
            df = df.with_columns([
                pl.col(birth_date_col).str.to_date().alias("_birth_date")
            ])

        # Parse hire dates if available
        if hire_date_col:
            try:
                df = df.with_columns([
                    pl.col(hire_date_col).cast(pl.Date).alias("_hire_date")
                ])
            except Exception:
                df = df.with_columns([
                    pl.col(hire_date_col).str.to_date().alias("_hire_date")
                ])

        # Filter to active employees if status column exists
        if "active" in df.columns:
            df = df.filter(pl.col("active") == True)  # noqa: E712
        elif "status" in df.columns:
            df = df.filter(pl.col("status").str.to_lowercase() == "active")

        # Filter to most recent calendar year of hires if hire date is available
        recent_hires_only = False
        recent_year = None
        if hire_date_col and "_hire_date" in df.columns:
            # Find the most recent calendar year with hires
            max_hire_date = df.select(pl.col("_hire_date").max()).item()
            if max_hire_date:
                recent_year = max_hire_date.year
                recent_hires = df.filter(pl.col("_hire_date").dt.year() == recent_year)
                if recent_hires.height >= 10:  # Need at least 10 recent hires for meaningful analysis
                    df = recent_hires
                    recent_hires_only = True

        # Calculate age at hire (if we have recent hires) or current age
        if recent_hires_only and "_hire_date" in df.columns:
            # Age at time of hire
            df = df.with_columns([
                ((pl.col("_hire_date") - pl.col("_birth_date")).dt.total_days() / 365.25)
                .floor()
                .cast(pl.Int32)
                .alias("_age")
            ])
        else:
            # Current age
            df = df.with_columns([
                ((pl.lit(today) - pl.col("_birth_date")).dt.total_days() / 365.25)
                .floor()
                .cast(pl.Int32)
                .alias("_age")
            ])

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

        total_count = len(df)
        if total_count == 0:
            raise ValueError(
                "No employees found. "
                + ("No hires in the last 12 months." if hire_date_col else "")
            )

        distribution = []
        for target_age, min_age, max_age, description in age_buckets:
            count = df.filter(
                (pl.col("_age") >= min_age) & (pl.col("_age") < max_age)
            ).height
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
        # Resolve path
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

        # Find compensation column
        comp_col = None
        for col_name in ["employee_gross_compensation", "annual_salary", "compensation", "salary", "base_salary"]:
            if col_name in df.columns:
                comp_col = col_name
                break

        if not comp_col:
            raise ValueError(
                "Census file must contain a compensation column "
                "(employee_gross_compensation, annual_salary, compensation, salary, or base_salary)"
            )

        # Find level column (optional - will still work without it)
        level_col = None
        for col_name in ["employee_job_level", "job_level", "level", "grade", "band"]:
            if col_name in df.columns:
                level_col = col_name
                break

        # Find hire date column for recent hires analysis
        hire_date_col = None
        for col_name in ["employee_hire_date", "hire_date", "hiredate", "start_date"]:
            if col_name in df.columns:
                hire_date_col = col_name
                break

        # Cast compensation to float
        try:
            df = df.with_columns([
                pl.col(comp_col).cast(pl.Float64).alias("_compensation")
            ])
            if level_col:
                df = df.with_columns([
                    pl.col(level_col).cast(pl.Int32).alias("_level")
                ])
        except Exception as e:
            raise ValueError(f"Failed to parse compensation data: {e}")

        # Filter to active employees if status column exists
        if "active" in df.columns:
            df = df.filter(pl.col("active") == True)  # noqa: E712
        elif "status" in df.columns:
            df = df.filter(pl.col("status").str.to_lowercase() == "active")

        # Try to parse hire dates and annualize compensation
        recent_hires_only = False
        lookback_description = None
        annualized = False

        if hire_date_col:
            try:
                df = df.with_columns([
                    pl.col(hire_date_col).cast(pl.Date).alias("_hire_date")
                ])
            except Exception:
                try:
                    df = df.with_columns([
                        pl.col(hire_date_col).str.to_date().alias("_hire_date")
                    ])
                except Exception:
                    # Can't parse dates, skip hire date processing
                    pass

            if "_hire_date" in df.columns:
                from datetime import timedelta, date

                # Find the "census date" - assume it's the max hire date or end of that year
                max_hire_date = df.select(pl.col("_hire_date").max()).item()
                if max_hire_date:
                    # Assume census is from end of the year of the most recent hire
                    census_date = date(max_hire_date.year, 12, 31)

                    # Calculate days worked in census year for each employee
                    # For employees hired in census year, annualize their compensation
                    df = df.with_columns([
                        # Days from hire to end of year (capped at 365)
                        pl.when(pl.col("_hire_date").dt.year() == census_date.year)
                        .then(
                            (pl.lit(census_date) - pl.col("_hire_date")).dt.total_days().clip(1, 365)
                        )
                        .otherwise(pl.lit(365))
                        .alias("_days_worked")
                    ])

                    # Annualize compensation: if worked partial year, scale up to full year
                    # Only annualize if days_worked < 365 and compensation seems prorated
                    df = df.with_columns([
                        pl.when(pl.col("_days_worked") < 365)
                        .then(pl.col("_compensation") * 365.0 / pl.col("_days_worked"))
                        .otherwise(pl.col("_compensation"))
                        .alias("_compensation_annualized")
                    ])

                    # Use annualized compensation for analysis
                    df = df.with_columns([
                        pl.col("_compensation_annualized").alias("_compensation")
                    ])
                    annualized = True

                    # Now filter to recent hires if requested
                    if lookback_years > 0:
                        cutoff_date = max_hire_date - timedelta(days=lookback_years * 365)
                        recent_hires = df.filter(pl.col("_hire_date") >= cutoff_date)

                        # Need enough data for meaningful analysis (at least 20 employees)
                        if recent_hires.height >= 20:
                            df = recent_hires
                            recent_hires_only = True
                            lookback_description = f"Hires from last {lookback_years} years ({recent_hires.height} employees, annualized)"
                        else:
                            lookback_description = f"All employees (only {recent_hires.height} recent hires found, need 20+)"

        # Filter out invalid compensation (after annualization)
        df = df.filter(pl.col("_compensation") > 0)
        # Also filter out unreasonably high annualized values (> $2M is likely an error)
        df = df.filter(pl.col("_compensation") < 2_000_000)

        total_count = len(df)
        if total_count == 0:
            raise ValueError("No employees with valid compensation data found")

        # If we have level data, calculate by level
        if level_col and "_level" in df.columns:
            level_stats = df.group_by("_level").agg([
                pl.col("_compensation").min().alias("min_comp"),
                pl.col("_compensation").max().alias("max_comp"),
                pl.col("_compensation").median().alias("median_comp"),
                pl.col("_compensation").quantile(0.25).alias("p25_comp"),
                pl.col("_compensation").quantile(0.75).alias("p75_comp"),
                pl.col("_compensation").mean().alias("avg_comp"),
                pl.col("_compensation").count().alias("employee_count"),
            ]).sort("_level")

            levels = []
            level_names = {1: "Staff", 2: "Manager", 3: "Sr Manager", 4: "Director", 5: "VP"}

            for row in level_stats.iter_rows(named=True):
                level_id = row["_level"]
                # Use P25-P75 as the recommended hiring range (more robust than min/max)
                # This avoids outliers at both ends and gives a realistic market range
                recommended_min = row["p25_comp"]
                recommended_max = row["p75_comp"]
                levels.append({
                    "level": level_id,
                    "name": level_names.get(level_id, f"Level {level_id}"),
                    "employee_count": row["employee_count"],
                    # Raw min/max for reference
                    "raw_min_compensation": round(row["min_comp"], 2),
                    "raw_max_compensation": round(row["max_comp"], 2),
                    # Recommended range (P25-P75) for new hire targeting
                    "min_compensation": round(recommended_min, 2),
                    "max_compensation": round(recommended_max, 2),
                    "median_compensation": round(row["median_comp"], 2),
                    "p25_compensation": round(row["p25_comp"], 2),
                    "p75_compensation": round(row["p75_comp"], 2),
                    "avg_compensation": round(row["avg_comp"], 2),
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
            # Use P5 and P97 to avoid outliers at the extremes
            overall_stats = df.select([
                pl.col("_compensation").min().alias("min_comp"),
                pl.col("_compensation").max().alias("max_comp"),
                pl.col("_compensation").median().alias("median_comp"),
                pl.col("_compensation").quantile(0.05).alias("p5_comp"),
                pl.col("_compensation").quantile(0.10).alias("p10_comp"),
                pl.col("_compensation").quantile(0.25).alias("p25_comp"),
                pl.col("_compensation").quantile(0.50).alias("p50_comp"),
                pl.col("_compensation").quantile(0.75).alias("p75_comp"),
                pl.col("_compensation").quantile(0.90).alias("p90_comp"),
                pl.col("_compensation").quantile(0.95).alias("p95_comp"),
                pl.col("_compensation").quantile(0.97).alias("p97_comp"),
                pl.col("_compensation").mean().alias("avg_comp"),
            ]).to_dicts()[0]

            # Create suggested level ranges based on percentiles
            # Use P5 as floor (not min) to avoid outliers dragging down Level 1
            # Use P97 as ceiling (not max) to avoid outliers inflating Level 5
            suggested_levels = [
                {
                    "level": 1,
                    "name": "Staff",
                    "suggested_min": round(overall_stats["p5_comp"], 0),
                    "suggested_max": round(overall_stats["p25_comp"], 0),
                    "percentile_range": "5th-25th",
                },
                {
                    "level": 2,
                    "name": "Manager",
                    "suggested_min": round(overall_stats["p25_comp"], 0),
                    "suggested_max": round(overall_stats["p50_comp"], 0),
                    "percentile_range": "25th-50th",
                },
                {
                    "level": 3,
                    "name": "Sr Manager",
                    "suggested_min": round(overall_stats["p50_comp"], 0),
                    "suggested_max": round(overall_stats["p75_comp"], 0),
                    "percentile_range": "50th-75th",
                },
                {
                    "level": 4,
                    "name": "Director",
                    "suggested_min": round(overall_stats["p75_comp"], 0),
                    "suggested_max": round(overall_stats["p90_comp"], 0),
                    "percentile_range": "75th-90th",
                },
                {
                    "level": 5,
                    "name": "VP",
                    "suggested_min": round(overall_stats["p90_comp"], 0),
                    "suggested_max": round(overall_stats["p97_comp"], 0),
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
                    "min_compensation": round(overall_stats["min_comp"], 2),
                    "max_compensation": round(overall_stats["max_comp"], 2),
                    "median_compensation": round(overall_stats["median_comp"], 2),
                    "p10_compensation": round(overall_stats["p10_comp"], 2),
                    "p25_compensation": round(overall_stats["p25_comp"], 2),
                    "p75_compensation": round(overall_stats["p75_comp"], 2),
                    "p90_compensation": round(overall_stats["p90_comp"], 2),
                    "avg_compensation": round(overall_stats["avg_comp"], 2),
                },
                "suggested_levels": suggested_levels,
                "source_file": str(file_path),
            }
