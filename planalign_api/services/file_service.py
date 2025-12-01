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
