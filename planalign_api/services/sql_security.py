"""SQL security utilities for preventing injection attacks.

This module provides validation and sanitization functions for use with
DuckDB queries where parameterized queries cannot be used (e.g., column names,
file paths in read_csv/read_parquet functions).

Security patterns implemented:
- Column name validation against allowlist pattern
- File path validation to prevent path traversal
- Numeric value validation for safe interpolation
"""

import re
from pathlib import Path
from typing import Optional, Set

# Valid SQL identifier pattern: alphanumeric and underscores, must start with letter/underscore
VALID_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Maximum identifier length (DuckDB limit)
MAX_IDENTIFIER_LENGTH = 255


class SQLSecurityError(ValueError):
    """Raised when a SQL security validation fails."""

    pass


def validate_column_name(column_name: str, context: str = "column") -> str:
    """
    Validate a column name is safe for SQL interpolation.

    Args:
        column_name: The column name to validate
        context: Description for error messages (e.g., "column", "table")

    Returns:
        The validated column name (unchanged if valid)

    Raises:
        SQLSecurityError: If the column name is invalid or potentially malicious
    """
    if not column_name:
        raise SQLSecurityError(f"Empty {context} name provided")

    if len(column_name) > MAX_IDENTIFIER_LENGTH:
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name[:50]}...': exceeds maximum length"
        )

    if not VALID_IDENTIFIER_PATTERN.match(column_name):
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name}': must contain only "
            "alphanumeric characters and underscores, starting with a letter or underscore"
        )

    # Additional check for SQL keywords that shouldn't be used as identifiers
    sql_keywords = {
        "select",
        "from",
        "where",
        "drop",
        "delete",
        "insert",
        "update",
        "create",
        "alter",
        "truncate",
        "execute",
        "exec",
        "union",
        "join",
    }
    if column_name.lower() in sql_keywords:
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name}': reserved SQL keyword"
        )

    return column_name


def validate_column_name_from_set(
    column_name: str, allowed_columns: Set[str], context: str = "column"
) -> str:
    """
    Validate a column name against an explicit allowlist.

    This is the strictest validation - only allows columns that are known safe.

    Args:
        column_name: The column name to validate
        allowed_columns: Set of allowed column names
        context: Description for error messages

    Returns:
        The validated column name

    Raises:
        SQLSecurityError: If the column name is not in the allowlist
    """
    # First validate the format
    validate_column_name(column_name, context)

    # Then check against allowlist
    if column_name not in allowed_columns:
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name}': not in allowed list"
        )

    return column_name


def validate_file_path(
    file_path: Path, allowed_root: Path, context: str = "file"
) -> Path:
    """
    Validate a file path is safe and within allowed directory.

    Prevents path traversal attacks by ensuring the resolved path
    is within the allowed root directory.

    Args:
        file_path: The file path to validate
        allowed_root: The root directory that paths must be within
        context: Description for error messages

    Returns:
        The validated, resolved path

    Raises:
        SQLSecurityError: If the path is invalid or outside allowed root
    """
    try:
        # Resolve to absolute path (handles .. and symlinks)
        resolved = file_path.resolve()
        allowed_resolved = allowed_root.resolve()

        # Check path is within allowed root
        try:
            resolved.relative_to(allowed_resolved)
        except ValueError:
            raise SQLSecurityError(
                f"Invalid {context} path: path traversal detected - "
                f"'{file_path}' is outside allowed directory"
            )

        return resolved

    except OSError as e:
        raise SQLSecurityError(f"Invalid {context} path '{file_path}': {e}")


def validate_file_path_for_sql(
    file_path: Path, allowed_roots: list[Path], context: str = "file"
) -> str:
    """
    Validate a file path and return a safe string for SQL interpolation.

    This is specifically for use in DuckDB's read_csv/read_parquet functions
    where parameterized queries cannot be used.

    Args:
        file_path: The file path to validate
        allowed_roots: List of allowed root directories
        context: Description for error messages

    Returns:
        The validated path as a string, safe for SQL interpolation

    Raises:
        SQLSecurityError: If the path is invalid or outside allowed roots
    """
    resolved = file_path.resolve()

    # Check against all allowed roots
    path_is_valid = False
    for allowed_root in allowed_roots:
        try:
            allowed_resolved = allowed_root.resolve()
            resolved.relative_to(allowed_resolved)
            path_is_valid = True
            break
        except (ValueError, OSError):
            continue

    if not path_is_valid:
        raise SQLSecurityError(
            f"Invalid {context} path: '{file_path}' is outside allowed directories"
        )

    # Check for SQL injection characters in the path string
    path_str = str(resolved)
    dangerous_patterns = ["'", '"', ";", "--", "/*", "*/", "\\x00"]
    for pattern in dangerous_patterns:
        if pattern in path_str:
            raise SQLSecurityError(
                f"Invalid {context} path: contains potentially dangerous character '{pattern}'"
            )

    return path_str


def validate_integer(value: int, min_val: Optional[int] = None, max_val: Optional[int] = None, context: str = "value") -> int:
    """
    Validate an integer value for safe SQL interpolation.

    Args:
        value: The integer value to validate
        min_val: Optional minimum allowed value
        max_val: Optional maximum allowed value
        context: Description for error messages

    Returns:
        The validated integer

    Raises:
        SQLSecurityError: If the value is not a valid integer or out of range
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise SQLSecurityError(f"Invalid {context}: must be an integer, got {type(value).__name__}")

    if min_val is not None and value < min_val:
        raise SQLSecurityError(f"Invalid {context}: {value} is less than minimum {min_val}")

    if max_val is not None and value > max_val:
        raise SQLSecurityError(f"Invalid {context}: {value} is greater than maximum {max_val}")

    return value


def validate_numeric(value: float, context: str = "value") -> float:
    """
    Validate a numeric value for safe SQL interpolation.

    Args:
        value: The numeric value to validate
        context: Description for error messages

    Returns:
        The validated numeric value

    Raises:
        SQLSecurityError: If the value is not a valid number
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SQLSecurityError(f"Invalid {context}: must be numeric, got {type(value).__name__}")

    # Check for special float values that could cause issues
    import math
    if math.isnan(value) or math.isinf(value):
        raise SQLSecurityError(f"Invalid {context}: NaN and Infinity are not allowed")

    return float(value)


# Common column name allowlists for census data
CENSUS_BIRTH_DATE_COLUMNS = frozenset({
    "employee_birth_date",
    "birth_date",
    "birthdate",
    "dob",
})

CENSUS_HIRE_DATE_COLUMNS = frozenset({
    "employee_hire_date",
    "hire_date",
    "hiredate",
    "start_date",
})

CENSUS_TERMINATION_DATE_COLUMNS = frozenset({
    "employee_termination_date",
    "termination_date",
    "term_date",
})

CENSUS_COMPENSATION_COLUMNS = frozenset({
    "employee_gross_compensation",
    "annual_salary",
    "compensation",
    "salary",
    "base_salary",
})

CENSUS_JOB_LEVEL_COLUMNS = frozenset({
    "employee_job_level",
    "job_level",
    "level",
    "grade",
    "band",
})

CENSUS_STATUS_COLUMNS = frozenset({
    "active",
    "status",
    "employment_status",
})

# All known safe census columns
ALL_CENSUS_COLUMNS = (
    CENSUS_BIRTH_DATE_COLUMNS
    | CENSUS_HIRE_DATE_COLUMNS
    | CENSUS_TERMINATION_DATE_COLUMNS
    | CENSUS_COMPENSATION_COLUMNS
    | CENSUS_JOB_LEVEL_COLUMNS
    | CENSUS_STATUS_COLUMNS
    | frozenset({"employee_id", "department", "location"})
)
